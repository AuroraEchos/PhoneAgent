from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phoneagent.runtime import AgentEvent, EventType
from webui.runtime import ConsoleRuntime, TrajectoryStore
from webui.server import ConsoleHTTPServer


def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for background web console state")


class _FakeState:
    def __init__(self) -> None:
        self.goal = ""
        self.success = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "success": self.success,
            "phase": "completed" if self.success else "failed",
            "current_step": 1,
            "current_app": "WeChat",
            "recovery_count": 0,
            "finished_at": time.time(),
            "last_thinking": "Open the requested app",
            "last_action": {"_metadata": "do", "action": "Launch", "app": "微信"},
            "last_verification": {
                "status": "passed",
                "command_success": True,
                "observable_effect_verified": True,
                "semantic_effect_verified": True,
            },
            "last_recovery": {},
        }


class _FakeAgent:
    def __init__(self, *, require_confirmation: bool = False, **callbacks: Any) -> None:
        self.event_callback = callbacks["event_callback"]
        self.confirmation_callback = callbacks["confirmation_callback"]
        self.require_confirmation = require_confirmation
        self.state = _FakeState()
        self.last_trajectory_path: str | None = None
        self.confirmed: bool | None = None

    def run(self, task: str) -> str:
        self.state.goal = task
        self.event_callback(
            AgentEvent(
                type=EventType.PHASE_CHANGE,
                message="Acquire current device state",
                payload={"current": "observing", "step": 1},
            )
        )
        self.event_callback(
            AgentEvent(
                type=EventType.MODEL_RESPONSE,
                message="Model response received",
                payload={"thinking": "Open the requested app", "step": 1},
            )
        )
        if self.require_confirmation:
            self.confirmed = self.confirmation_callback("提交订单")
            self.state.success = self.confirmed
        return "done" if self.state.success else "cancelled"


def _device_check(_device_id: str | None) -> tuple[bool, str | None]:
    print("[1/4] ADB executable\n  [OK] Android Debug Bridge")
    print("[2/4] Connected device\n  [OK] device ready\n  Selected: test-device")
    print("[3/4] Text input method\n  [WARN] ADB Keyboard is not installed")
    print("[4/4] Visual observation\n  [OK] screenshot=1080x2400")
    return True, "test-device"


def _model_check(_config: Any) -> bool:
    print("Model API Check\n  [OK] API responded")
    return True


def test_console_checks_once_and_reuses_agent_for_tasks(tmp_path: Path) -> None:
    created: list[_FakeAgent] = []
    device_calls = 0
    model_calls = 0

    def device_checker(device_id: str | None) -> tuple[bool, str | None]:
        nonlocal device_calls
        device_calls += 1
        return _device_check(device_id)

    def model_checker(config: Any) -> bool:
        nonlocal model_calls
        model_calls += 1
        return _model_check(config)

    def factory(**kwargs: Any) -> _FakeAgent:
        agent = _FakeAgent(**kwargs)
        created.append(agent)
        return agent

    runtime = ConsoleRuntime(
        tmp_path,
        agent_factory=factory,
        device_checker=device_checker,
        model_checker=model_checker,
    )
    assert runtime.start_checks() is True
    _wait_for(lambda: runtime.snapshot()["startup"]["status"] == "ready")

    startup = runtime.snapshot()["startup"]
    statuses = {item["id"]: item["status"] for item in startup["checks"]}
    assert statuses == {
        "adb": "passed",
        "device": "passed",
        "keyboard": "warning",
        "screenshot": "passed",
        "model": "passed",
    }
    assert startup["device_id"] == "test-device"

    runtime.start_task("first task")
    _wait_for(lambda: runtime.snapshot()["task"]["status"] == "success")
    runtime.start_task("second task")
    _wait_for(lambda: runtime.snapshot()["task"]["status"] == "success")

    assert len(created) == 1
    assert device_calls == 1
    assert model_calls == 1
    assert runtime.snapshot()["startup"]["reused"] is True
    runtime.close()


def test_sensitive_confirmation_round_trip(tmp_path: Path) -> None:
    created: list[_FakeAgent] = []

    def factory(**kwargs: Any) -> _FakeAgent:
        agent = _FakeAgent(require_confirmation=True, **kwargs)
        created.append(agent)
        return agent

    runtime = ConsoleRuntime(
        tmp_path,
        agent_factory=factory,
        device_checker=_device_check,
        model_checker=_model_check,
    )
    runtime.start_checks()
    _wait_for(lambda: runtime.snapshot()["startup"]["status"] == "ready")
    runtime.start_task("place an order")
    _wait_for(lambda: runtime.snapshot()["pending_prompt"] is not None)

    snapshot = runtime.snapshot()
    assert snapshot["task"]["status"] == "waiting_user"
    prompt = snapshot["pending_prompt"]
    assert prompt["type"] == "confirmation"
    runtime.respond_prompt(prompt["id"], True)
    _wait_for(lambda: runtime.snapshot()["task"]["status"] == "success")

    assert created[0].confirmed is True
    assert runtime.snapshot()["pending_prompt"] is None
    runtime.close()


def test_trajectory_store_lists_reads_and_rejects_traversal(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    path = runs / "trajectory_abc123.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": "abc123",
                "task": "open WeChat",
                "success": True,
                "event_count": 2,
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    store = TrajectoryStore(runs)

    assert store.list()[0]["task"] == "open WeChat"
    assert store.read(path.name)["run_id"] == "abc123"
    with pytest.raises(ValueError):
        store.read("../trajectory_abc123.json")


def test_http_console_serves_frontend_and_accepts_task(tmp_path: Path) -> None:
    runtime = ConsoleRuntime(
        tmp_path,
        agent_factory=lambda **kwargs: _FakeAgent(**kwargs),
        device_checker=_device_check,
        model_checker=_model_check,
    )
    runtime.start_checks()
    _wait_for(lambda: runtime.snapshot()["startup"]["status"] == "ready")
    server = ConsoleHTTPServer(("127.0.0.1", 0), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base_url}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "PhoneAgent Web Console" in html
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

        request = Request(
            f"{base_url}/api/tasks",
            data=json.dumps({"task": "open WeChat"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 202
        _wait_for(lambda: runtime.snapshot()["task"]["status"] == "success")

        with urlopen(f"{base_url}/api/state", timeout=2) as response:
            state = json.loads(response.read())
            assert state["task"]["goal"] == "open WeChat"
            assert state["task"]["status"] == "success"
    finally:
        server.shutdown()
        server.server_close()
        runtime.close()
        thread.join(timeout=2)
