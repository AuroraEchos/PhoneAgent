from __future__ import annotations

import json

from phoneagent.runtime import TrajectoryRecorder


def test_trajectory_is_saved_as_valid_json(tmp_path) -> None:
    recorder = TrajectoryRecorder(output_dir=str(tmp_path), task="test")
    recorder.add("observation", {"ratio": float("nan")}, step=1)
    recorder.mark_finished(success=True, message="done")
    path = recorder.save(state={"phase": "completed"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["success"] is True
    assert payload["events"][0]["payload"]["ratio"] is None
    assert not list(tmp_path.glob("*.tmp"))
