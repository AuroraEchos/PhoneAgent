from __future__ import annotations

from dataclasses import dataclass

from phoneagent import AgentConfig, PhoneAgent
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

    def request(self, messages, print_stream=False) -> ModelResponse:
        return self.responses.pop(0)


def test_agent_loop_reuses_verified_observation_and_finishes(tmp_path) -> None:
    device = FakeDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="tap",
                action='do(action="Tap", element=[500, 500])',
                raw_content='<think>tap</think><answer>do(action="Tap", element=[500, 500])</answer>',
            ),
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='<think>done</think><answer>finish(message="done", success=True)</answer>',
            ),
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=4,
            verbose=False,
            app_awareness_enabled=False,
            inject_app_context=False,
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
    assert agent.state.last_verification["observable_effect_verified"] is True
    assert agent.state.last_verification["semantic_effect_verified"] is None
