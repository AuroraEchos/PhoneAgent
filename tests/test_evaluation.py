from __future__ import annotations

import json
from pathlib import Path

import pytest

from phoneagent.evaluation import (
    build_evaluation_report,
    discover_trajectory_paths,
    load_annotations,
    load_trajectory,
    main,
    summarize_trajectory,
)


def trajectory(run_id: str = "run-1") -> dict:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "task": "打开设置",
        "duration_seconds": 8.0,
        "success": True,
        "state": {"current_step": 2},
        "events": [
            {"type": "model_request", "step": 1, "payload": {}},
            {
                "type": "model_response",
                "step": 1,
                "payload": {
                    "metrics": {
                        "total_time": 1.5,
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    }
                },
            },
            {
                "type": "action",
                "step": 1,
                "payload": {"action": {"_metadata": "do", "action": "Tap"}},
            },
            {
                "type": "verification",
                "step": 1,
                "payload": {"error_code": "verification_no_effect"},
            },
            {"type": "recovery", "step": 1, "payload": {"stage": "outcome"}},
            {"type": "model_request", "step": 2, "payload": {}},
            {
                "type": "model_response",
                "step": 2,
                "payload": {
                    "metrics": {
                        "total_time": 0.5,
                        "prompt_tokens": 80,
                        "completion_tokens": 10,
                        "total_tokens": 90,
                    }
                },
            },
            {
                "type": "action",
                "step": 2,
                "payload": {"action": {"_metadata": "finish", "success": True}},
            },
        ],
    }


def test_summary_keeps_runtime_and_task_success_separate() -> None:
    without_judgment = summarize_trajectory(trajectory())
    judged = summarize_trajectory(
        trajectory(),
        {"task_success": False, "domain": "设备与系统", "notes": "停留页面错误"},
    )

    assert without_judgment["runtime_success"] is True
    assert without_judgment["task_success"] is None
    assert judged["runtime_success"] is True
    assert judged["task_success"] is False
    assert judged["steps"] == 2
    assert judged["model_requests"] == 2
    assert judged["model_time_seconds"] == pytest.approx(2.0)
    assert judged["total_tokens"] == 210
    assert judged["actions"] == {"Finish": 1, "Tap": 1}
    assert judged["recoveries"] == 1
    assert judged["error_codes"] == {"verification_no_effect": 1}


def test_report_rates_only_use_externally_judged_runs() -> None:
    second = trajectory("run-2")
    second["success"] = False
    report = build_evaluation_report(
        [trajectory(), second],
        {"run-1": {"task_success": False}},
    )

    aggregate = report["aggregate"]
    assert aggregate["total_runs"] == 2
    assert aggregate["runtime_success_rate"] == pytest.approx(0.5)
    assert aggregate["human_evaluated_runs"] == 1
    assert aggregate["task_success_rate"] == pytest.approx(0.0)
    assert aggregate["total_model_requests"] == 4
    assert aggregate["total_model_time_seconds"] == pytest.approx(4.0)
    assert aggregate["total_tokens"] == 420


def test_summary_reports_semantic_review_request_purposes_and_verdicts() -> None:
    reviewed = trajectory()
    reviewed["events"].extend(
        [
            {
                "type": "model_request",
                "step": 2,
                "payload": {"purpose": "task_completion"},
            },
            {
                "type": "task_verification",
                "step": 2,
                "payload": {"verdict": "pass"},
            },
            {
                "type": "risk_review",
                "step": 1,
                "payload": {"verdict": "confirm"},
            },
        ]
    )

    summary = summarize_trajectory(reviewed)

    assert summary["model_requests"] == 3
    assert summary["model_request_purposes"] == {
        "planning": 2,
        "task_completion": 1,
    }
    assert summary["task_verification_verdicts"] == {"pass": 1}
    assert summary["risk_review_verdicts"] == {"confirm": 1}


def test_loaders_validate_inputs_and_cli_writes_report(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    trajectory_path = runs / "trajectory_run-1.json"
    trajectory_path.write_text(json.dumps(trajectory()), encoding="utf-8")
    (runs / "unrelated.json").write_text("{}", encoding="utf-8")
    annotations_path = tmp_path / "annotations.json"
    annotations_path.write_text(
        json.dumps({"runs": {"run-1": {"task_success": True}}}),
        encoding="utf-8",
    )
    output = tmp_path / "reports" / "baseline.json"

    assert discover_trajectory_paths([runs]) == [trajectory_path.resolve()]
    assert load_trajectory(trajectory_path)["run_id"] == "run-1"
    assert load_annotations(annotations_path)["run-1"]["task_success"] is True
    assert main(
        [str(runs), "--annotations", str(annotations_path), "--output", str(output)]
    ) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["aggregate"]["task_success_rate"] == 1.0
    assert json.loads(capsys.readouterr().out)["aggregate"]["total_runs"] == 1


def test_invalid_annotation_cannot_claim_non_boolean_success(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations.json"
    annotations.write_text(
        json.dumps({"run-1": {"task_success": "yes"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="true, false, or null"):
        load_annotations(annotations)


def test_report_rejects_duplicate_run_ids_and_reports_unmatched_annotations() -> None:
    with pytest.raises(ValueError, match="Duplicate trajectory run_id"):
        build_evaluation_report([trajectory(), trajectory()])

    report = build_evaluation_report(
        [trajectory()],
        {"not-in-this-session": {"task_success": True}},
    )
    assert report["unmatched_annotation_run_ids"] == ["not-in-this-session"]
