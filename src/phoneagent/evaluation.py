"""Offline trajectory summaries for reproducible PhoneAgent evaluations."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4


REPORT_SCHEMA_VERSION = "1.0"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _finite_number(value)
    return int(number) if number is not None else None


def discover_trajectory_paths(inputs: Iterable[str | Path]) -> list[Path]:
    """Resolve files and directories to unique trajectory JSON paths."""
    paths: set[Path] = set()
    for raw_path in inputs:
        path = Path(raw_path).expanduser().resolve()
        if path.is_dir():
            paths.update(item for item in path.glob("trajectory_*.json") if item.is_file())
        elif path.is_file():
            paths.add(path)
        else:
            raise FileNotFoundError(path)
    return sorted(paths)


def load_trajectory(path: str | Path) -> dict[str, Any]:
    """Load one trajectory and reject documents without the stable core contract."""
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid trajectory JSON: {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Trajectory must be a JSON object: {source}")
    if not isinstance(data.get("run_id"), str) or not data["run_id"].strip():
        raise ValueError(f"Trajectory is missing run_id: {source}")
    if not isinstance(data.get("events"), list):
        raise ValueError(f"Trajectory is missing its event stream: {source}")
    return data


def load_annotations(path: str | Path | None) -> dict[str, dict[str, Any]]:
    """Load optional human task-level judgments keyed by trajectory run ID."""
    if path is None:
        return {}
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "runs" in data:
        data = data["runs"]
    if not isinstance(data, dict):
        raise ValueError("Annotations must be an object keyed by run_id")

    annotations: dict[str, dict[str, Any]] = {}
    for run_id, annotation in data.items():
        if not isinstance(annotation, dict):
            raise ValueError(f"Annotation for {run_id!r} must be an object")
        task_success = annotation.get("task_success")
        if task_success is not None and not isinstance(task_success, bool):
            raise ValueError(f"task_success for {run_id!r} must be true, false, or null")
        annotations[str(run_id)] = dict(annotation)
    return annotations


def summarize_trajectory(
    trajectory: dict[str, Any],
    annotation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce one provider-neutral run summary from the authoritative event stream."""
    events = [event for event in trajectory.get("events", []) if isinstance(event, dict)]
    event_steps = [
        step
        for event in events
        if (step := _integer(event.get("step"))) is not None
    ]
    state = trajectory.get("state") if isinstance(trajectory.get("state"), dict) else {}
    state_step = _integer(state.get("current_step"))
    steps = max([*event_steps, state_step or 0], default=0)

    model_requests = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    model_time_seconds = 0.0
    token_fields_available: set[str] = set()
    model_time_available = False
    error_codes: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    recoveries = 0

    for event in events:
        event_type = str(event.get("type", ""))
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "model_request":
            model_requests += 1
        elif event_type == "model_response":
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            for field_name, accumulator in (
                ("prompt_tokens", "prompt"),
                ("completion_tokens", "completion"),
                ("total_tokens", "total"),
            ):
                value = _integer(metrics.get(field_name))
                if value is None:
                    continue
                token_fields_available.add(accumulator)
                if accumulator == "prompt":
                    prompt_tokens += value
                elif accumulator == "completion":
                    completion_tokens += value
                else:
                    total_tokens += value
            request_time = _finite_number(metrics.get("total_time"))
            if request_time is not None:
                model_time_available = True
                model_time_seconds += request_time
        elif event_type == "action":
            action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
            name = "Finish" if action.get("_metadata") == "finish" else action.get("action")
            if name:
                action_counts[str(name)] += 1
        elif event_type == "recovery" and payload.get("stage") == "outcome":
            recoveries += 1

        error_code = payload.get("error_code")
        if error_code:
            error_codes[str(error_code)] += 1

    if "total" not in token_fields_available and token_fields_available & {"prompt", "completion"}:
        total_tokens = prompt_tokens + completion_tokens
        token_fields_available.add("total")

    annotation = dict(annotation or {})
    task_success = annotation.get("task_success")
    return {
        "run_id": str(trajectory.get("run_id", "")),
        "trajectory_schema_version": str(trajectory.get("schema_version", "")),
        "task": str(trajectory.get("task", "")),
        "domain": annotation.get("domain"),
        "runtime_success": trajectory.get("success") is True,
        # Only an external judgment may populate task_success. Runtime finish is not proof.
        "task_success": task_success if isinstance(task_success, bool) else None,
        "annotation_notes": str(annotation.get("notes", "")),
        "duration_seconds": _finite_number(trajectory.get("duration_seconds")),
        "steps": steps,
        "model_requests": model_requests,
        "model_time_seconds": model_time_seconds if model_time_available else None,
        "prompt_tokens": prompt_tokens if "prompt" in token_fields_available else None,
        "completion_tokens": completion_tokens if "completion" in token_fields_available else None,
        "total_tokens": total_tokens if "total" in token_fields_available else None,
        "actions": dict(sorted(action_counts.items())),
        "recoveries": recoveries,
        "error_codes": dict(sorted(error_codes.items())),
    }


def build_evaluation_report(
    trajectories: Iterable[dict[str, Any]],
    annotations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate runtime evidence without treating model finish as semantic correctness."""
    annotation_map = annotations or {}
    trajectory_list = list(trajectories)
    run_ids = [str(item.get("run_id", "")) for item in trajectory_list]
    duplicates = sorted(run_id for run_id, count in Counter(run_ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate trajectory run_id values: {', '.join(duplicates)}")
    runs = [
        summarize_trajectory(item, annotation_map.get(str(item.get("run_id", ""))))
        for item in trajectory_list
    ]
    runtime_successes = sum(run["runtime_success"] is True for run in runs)
    judged = [run for run in runs if run["task_success"] is not None]
    task_successes = sum(run["task_success"] is True for run in judged)
    durations = [run["duration_seconds"] for run in runs if run["duration_seconds"] is not None]
    model_times = [
        run["model_time_seconds"] for run in runs if run["model_time_seconds"] is not None
    ]
    token_totals = [run["total_tokens"] for run in runs if run["total_tokens"] is not None]
    all_errors: Counter[str] = Counter()
    for run in runs:
        all_errors.update(run["error_codes"])

    total = len(runs)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "runtime_success": "The runtime accepted finish(success=True); not task correctness.",
            "task_success": "External human or deterministic evaluator judgment from annotations.",
        },
        "unmatched_annotation_run_ids": sorted(set(annotation_map) - set(run_ids)),
        "aggregate": {
            "total_runs": total,
            "runtime_successes": runtime_successes,
            "runtime_success_rate": runtime_successes / total if total else None,
            "human_evaluated_runs": len(judged),
            "task_successes": task_successes,
            "task_success_rate": task_successes / len(judged) if judged else None,
            "average_duration_seconds": mean(durations) if durations else None,
            "average_steps": mean(run["steps"] for run in runs) if runs else None,
            "total_model_requests": sum(run["model_requests"] for run in runs),
            "total_model_time_seconds": sum(model_times) if model_times else None,
            "total_tokens": sum(token_totals) if token_totals else None,
            "total_recoveries": sum(run["recoveries"] for run in runs),
            "error_codes": dict(sorted(all_errors.items())),
        },
        "runs": runs,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="phoneagent-eval",
        description="Summarize PhoneAgent trajectories without conflating runtime and task success.",
    )
    parser.add_argument("paths", nargs="+", help="Trajectory JSON files or directories")
    parser.add_argument("--annotations", help="Optional human judgments keyed by run_id")
    parser.add_argument("--output", help="Write the JSON report atomically to this path")
    args = parser.parse_args(argv)

    try:
        paths = discover_trajectory_paths(args.paths)
        if not paths:
            raise ValueError("No trajectory_*.json files were found")
        trajectories = [load_trajectory(path) for path in paths]
        annotations = load_annotations(args.annotations)
        report = build_evaluation_report(trajectories, annotations)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            _write_report(Path(args.output), report)
        print(rendered)
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"phoneagent-eval: error: {exc}\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
