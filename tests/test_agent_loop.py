from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from phoneagent import AgentConfig, PhoneAgent
from phoneagent.devices import AppLaunchResult
from phoneagent.model import ModelResponse
from phoneagent.runtime import RecoveryConfig, VerificationConfig

from conftest import make_observation


class FakeDevice:
    def __init__(self) -> None:
        self.screen_value = 10
        self.taps: list[tuple[int, int]] = []

    def observe(self):
        return make_observation(
            self.screen_value,
            app="Example",
            package="com.example",
        )

    def tap(self, x: int, y: int) -> None:
        self.taps.append((x, y))
        self.screen_value = 80

    def double_tap(self, x: int, y: int) -> None:  # pragma: no cover - adapter completeness
        self.tap(x, y)

    def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        self.tap(x, y)

    def swipe(self, *args, **kwargs) -> None:
        self.screen_value = 80

    def back(self) -> None:
        self.screen_value = 80

    def home(self) -> None:
        self.screen_value = 80

    def launch_app(self, app_name: str) -> bool:
        return True

    def type_text(self, text: str) -> None:
        self.screen_value = 80

    def clear_text(self) -> None:
        pass

    def detect_and_set_adb_keyboard(self) -> str:
        return ""

    def restore_keyboard(self, ime: str) -> None:
        pass


@dataclass
class FakeModelClient:
    responses: list[ModelResponse]
    requests: list[list[dict]] = field(default_factory=list)

    def request(self, messages, print_stream=False) -> ModelResponse:
        self.requests.append(copy.deepcopy(messages))
        return self.responses.pop(0)


class LazyLaunchDevice(FakeDevice):
    def __init__(self) -> None:
        super().__init__()
        self.launched = False
        self.launch_calls: list[str] = []

    def observe(self):
        if self.launched:
            return make_observation(80, app="WeChat", package="com.tencent.mm")
        return make_observation(10, app="System Home", package="com.android.launcher")

    def launch_app_resolved(self, query: str) -> AppLaunchResult:
        self.launch_calls.append(query)
        self.launched = True
        return AppLaunchResult(
            query=query,
            success=True,
            message="launched",
            package_name="com.tencent.mm",
            display_name="微信",
            metadata={"launch_mode": "test"},
        )


def test_agent_loop_reuses_verified_observation_and_finishes(tmp_path) -> None:
    device = FakeDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="tap",
                action='do(action="Tap", element=[500, 500])',
                raw_content='<answer>do(action="Tap", element=[500, 500])</answer>',
            ),
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='<answer>finish(message="done", success=True)</answer>',
            ),
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=4,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(
                settle_delay_seconds=0,
                observation_retries=0,
                visual_change_threshold=0.001,
            ),
            recovery=RecoveryConfig(retry_delay_seconds=0),
        ),
        device=device,
        model_client=model,
    )

    message = agent.run("tap the target")

    assert message == "done"
    assert agent.state.success is True
    assert device.taps == [(32, 32)]
    assert agent.last_trajectory_path is not None
    trajectory = json.loads(Path(agent.last_trajectory_path).read_text(encoding="utf-8"))
    verification = next(
        event["payload"] for event in trajectory["events"] if event["type"] == "verification"
    )
    assert verification["observable_effect_verified"] is True
    assert verification["semantic_effect_verified"] is None


def test_compound_task_launches_after_model_action(tmp_path) -> None:
    device = LazyLaunchDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="open WeChat",
                action='do(action="Launch", app="微信")',
                raw_content='<answer>do(action="Launch", app="微信")</answer>',
            ),
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='<answer>finish(message="done", success=True)</answer>',
            ),
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=3,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
            recovery=RecoveryConfig(retry_delay_seconds=0),
        ),
        device=device,  # type: ignore[arg-type]
        model_client=model,
    )

    message = agent.run("打开微信给张三发消息")

    assert message == "done"
    assert device.launch_calls == ["微信"]
    assert agent.step_count == 2
    assert "打开微信给张三发消息" in str(model.requests[0])
    action_events = [event for event in agent.trajectory.events if event["type"] == "action"]
    assert action_events[0]["payload"]["action"]["action"] == "Launch"
    assert action_events[0]["payload"]["action"]["app"] == "微信"


def test_open_only_task_uses_model_then_finishes_on_verified_screen(tmp_path) -> None:
    device = LazyLaunchDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="open WeChat",
                action='do(action="Launch", app="微信")',
                raw_content='<answer>do(action="Launch", app="微信")</answer>',
            ),
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='<answer>finish(message="done", success=True)</answer>',
            ),
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=2,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
        ),
        device=device,  # type: ignore[arg-type]
        model_client=model,
    )

    message = agent.run("打开微信")

    assert message == "done"
    assert device.launch_calls == ["微信"]
    assert len(model.requests) == 2
    assert agent.step_count == 2
