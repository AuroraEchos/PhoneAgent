"""Trajectory recording utilities for PhoneAgent."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class TrajectoryRecorder:
    """Persist an agent run as a structured and atomically-written trajectory."""

    output_dir: str = "runs"
    task: str = ""
    run_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    success: bool | None = None
    final_message: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    saved_path: str | None = None
    schema_version: str = "1.0"

    def add(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        step: int | None = None,
        message: str = "",
    ) -> None:
        event: dict[str, Any] = {
            "timestamp": time.time(),
            "type": event_type,
            "message": message,
            "payload": _json_safe(payload or {}),
        }
        if step is not None:
            event["step"] = step
        self.events.append(event)

    def mark_finished(self, *, success: bool, message: str | None) -> None:
        self.finished_at = time.time()
        self.success = success
        self.final_message = message or ""

    def to_dict(self, *, state: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "task": self.task,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": (
                self.finished_at - self.started_at if self.finished_at is not None else None
            ),
            "success": self.success,
            "final_message": self.final_message,
            "event_count": len(self.events),
            "events": self.events,
        }
        if state is not None:
            payload["state"] = _json_safe(state)
        return payload

    def save(self, *, state: dict[str, Any] | None = None) -> Path:
        directory = Path(self.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        final_path = directory / f"trajectory_{self.run_id}.json"
        temp_path = directory / f".{final_path.name}.{uuid4().hex}.tmp"
        data = json.dumps(
            self.to_dict(state=state),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        temp_path.write_text(data, encoding="utf-8")
        os.replace(temp_path, final_path)
        self.saved_path = str(final_path)
        return final_path


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return repr(value)
