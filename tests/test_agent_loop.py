from __future__ import annotations

import asyncio
import copy
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from phoneagent import AgentConfig, PhoneAgent
from phoneagent.devices import AppLaunchResult, SystemPanelCommandResult
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


class BlockingModelClient:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def request(self, messages, print_stream=False) -> ModelResponse:
        del messages, print_stream
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test model was not released")
        return ModelResponse(
            thinking="tap",
            action='do(action="Tap", element=[500, 500])',
            raw_content='do(action="Tap", element=[500, 500])',
        )


class BlockingAsyncModelClient:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.cancelled = threading.Event()

    async def request(self, messages, print_stream=False, cancel_event=None) -> ModelResponse:
        del messages, print_stream, cancel_event
        import asyncio

        self.entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()


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


class UninstalledLaunchDevice(LazyLaunchDevice):
    def launch_app_resolved(self, query: str) -> AppLaunchResult:
        self.launch_calls.append(query)
        return AppLaunchResult(
            query=query,
            success=False,
            message="not installed",
            package_name="com.tencent.mm",
            display_name="微信",
            error_code="app_not_installed",
        )


class PanelFallbackDevice(FakeDevice):
    def __init__(self) -> None:
        super().__init__()
        self.panel_visible = False
        self.primary_calls = 0
        self.fallback_calls = 0

    def observe(self):
        observation = make_observation(
            self.screen_value,
            app=(
                "Unknown (com.android.systemui)" if self.panel_visible else "Example"
            ),
            package="com.android.systemui" if self.panel_visible else "com.example",
        )
        observation.system_panel_visible = self.panel_visible
        observation.system_panel_name = "notificationshade"
        return observation

    def open_quick_settings(self) -> SystemPanelCommandResult:
        self.primary_calls += 1
        return SystemPanelCommandResult(
            target="quick_settings",
            command="expand-settings",
            success=True,
            returncode=0,
            message="accepted but ignored by OEM",
        )

    def open_system_panel_gesture(self, action_name, width, height):
        self.fallback_calls += 1
        self.panel_visible = True
        self.screen_value = 80
        return {
            "target": "quick_settings",
            "transport": "gesture",
            "fallback_used": True,
            "edge": "top_right",
            "start": [width - 1, 1],
            "end": [width - 1, height - 1],
        }


class TransientObservationFailureDevice(FakeDevice):
    def __init__(self) -> None:
        super().__init__()
        self.observe_calls = 0

    def observe(self):
        self.observe_calls += 1
        if self.observe_calls == 1:
            raise TimeoutError("injected screenshot timeout")
        return super().observe()


class FailingTapDevice(FakeDevice):
    def __init__(self) -> None:
        super().__init__()
        self.tap_attempts = 0

    def tap(self, x: int, y: int) -> None:
        del x, y
        self.tap_attempts += 1
        raise ConnectionError("injected ADB disconnect")


def test_public_async_run_and_step_match_terminal_sync_contract(tmp_path) -> None:
    async def exercise() -> None:
        config = AgentConfig(
            max_steps=1,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
        )
        response = ModelResponse(
            thinking="done",
            action='finish(message="done", success=True)',
            raw_content='finish(message="done", success=True)',
        )
        run_agent = PhoneAgent(
            agent_config=config,
            device=FakeDevice(),
            model_client=FakeModelClient([response]),
        )
        step_agent = PhoneAgent(
            agent_config=config,
            device=FakeDevice(),
            model_client=FakeModelClient([copy.deepcopy(response)]),
        )

        assert await run_agent.run_async("inspect screen") == "done"
        step_result = await step_agent.step_async("inspect screen")

        assert step_result.success is True
        assert step_result.finished is True
        assert step_result.message == "done"
        assert run_agent.state.phase.value == "completed"
        assert step_agent.state.phase.value == "completed"

    asyncio.run(exercise())


def test_agent_loop_reuses_verified_observation_and_finishes(tmp_path) -> None:
    device = FakeDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="tap",
                action='do(action="Tap", element=[500, 500])',
                raw_content='do(action="Tap", element=[500, 500])',
            ),
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='finish(message="done", success=True)',
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


def test_quick_settings_falls_back_inside_runtime_after_no_ui_effect(tmp_path) -> None:
    device = PanelFallbackDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="open quick settings",
                action='do(action="OpenQuickSettings")',
                raw_content='do(action="OpenQuickSettings")',
            )
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=2,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
            recovery=RecoveryConfig(retry_delay_seconds=0),
        ),
        device=device,  # type: ignore[arg-type]
        model_client=model,
    )

    result = agent.step("打开控制中心")

    assert result.success is True
    assert result.command_success is True
    assert result.verification is not None
    assert result.verification["semantic_effect_verified"] is True
    assert device.primary_calls == 1
    assert device.fallback_calls == 1
    execution_events = [
        event for event in agent.trajectory.events if event["type"] == "execution"
    ]
    assert len(execution_events) == 2
    assert execution_events[-1]["payload"]["metadata"]["internal_fallback"] is True


def test_agent_cooperatively_cancels_after_blocking_model_returns(tmp_path) -> None:
    device = FakeDevice()
    model = BlockingModelClient()
    agent = PhoneAgent(
        agent_config=AgentConfig(
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
        ),
        device=device,
        model_client=model,
    )
    result: list[str] = []
    thread = threading.Thread(target=lambda: result.append(agent.run("tap the target")))
    thread.start()
    assert model.entered.wait(timeout=30)

    assert agent.request_cancel("cancelled from test") is True
    model.release.set()
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert result == ["cancelled from test"]
    assert agent.state.phase.value == "cancelled"
    assert agent.state.success is False
    assert device.taps == []
    finish_event = next(event for event in agent.trajectory.events if event["type"] == "finish")
    assert finish_event["payload"]["error_code"] == "cancelled"


def test_agent_cancels_native_async_model_request_immediately(tmp_path) -> None:
    device = FakeDevice()
    model = BlockingAsyncModelClient()
    agent = PhoneAgent(
        agent_config=AgentConfig(
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
        ),
        device=device,
        model_client=FakeModelClient([]),
        async_model_client=model,  # type: ignore[arg-type]
    )
    result: list[str] = []
    thread = threading.Thread(target=lambda: result.append(agent.run("tap the target")))
    thread.start()
    assert model.entered.wait(timeout=30)

    assert agent.request_cancel("cancelled during stream") is True
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert model.cancelled.is_set()
    assert result == ["cancelled during stream"]
    assert agent.state.phase.value == "cancelled"


def test_coordinate_signature_only_tracks_coordinate_actions() -> None:
    first_tap = PhoneAgent._action_coordinate_signature(
        {"action": "Tap", "element": [250, 126], "description": "first"}
    )
    second_tap = PhoneAgent._action_coordinate_signature(
        {"action": "Tap", "element": [250.0, 126.0], "description": "second"}
    )

    assert first_tap == second_tap
    assert PhoneAgent._action_coordinate_signature({"action": "Type", "text": "北京"}) == ""
    assert PhoneAgent._action_coordinate_signature({"action": "Launch", "app": "微信"}) == ""


def test_compound_task_launches_before_first_model_action(tmp_path) -> None:
    device = LazyLaunchDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='finish(message="done", success=True)',
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
    assert action_events[0]["payload"]["source"] == "runtime_initial_launch"
    assert not any(
        event["type"] == "model_request" and event["step"] == 1 for event in agent.trajectory.events
    )


def test_open_only_task_skips_model_for_initial_launch(tmp_path) -> None:
    device = LazyLaunchDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="done",
                action='finish(message="done", success=True)',
                raw_content='finish(message="done", success=True)',
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
    assert len(model.requests) == 1
    assert agent.step_count == 2


def test_initial_launch_is_skipped_when_target_is_already_foreground(tmp_path) -> None:
    device = LazyLaunchDevice()
    device.launched = True
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="already open",
                action='finish(message="done", success=True)',
                raw_content='finish(message="done", success=True)',
            )
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=1,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
        ),
        device=device,  # type: ignore[arg-type]
        model_client=model,
    )

    assert agent.run("打开微信") == "done"
    assert device.launch_calls == []
    assert len(model.requests) == 1


def test_failed_initial_launch_returns_control_to_model(tmp_path) -> None:
    device = UninstalledLaunchDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="use a visible fallback",
                action='finish(message="fallback considered", success=False)',
                raw_content='finish(message="fallback considered", success=False)',
            )
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=2,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
            recovery=RecoveryConfig(retry_delay_seconds=0),
        ),
        device=device,  # type: ignore[arg-type]
        model_client=model,
    )

    first = agent.step("打开微信")
    second = agent.step()

    assert first.error_code == "app_not_installed"
    assert first.finished is False
    assert second.message == "fallback considered"
    assert device.launch_calls == ["微信"]
    assert len(model.requests) == 1
    assert "app_not_installed" in str(model.requests[0])


def test_observation_timeout_is_reobserved_before_model_planning(tmp_path) -> None:
    device = TransientObservationFailureDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="done after fresh observation",
                action='finish(message="done", success=True)',
                raw_content='finish(message="done", success=True)',
            )
        ]
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            max_steps=3,
            observation_retries=0,
            observation_retry_delay=0,
            verbose=False,
            trajectory_dir=str(tmp_path),
            verification=VerificationConfig(settle_delay_seconds=0, observation_retries=0),
            recovery=RecoveryConfig(retry_delay_seconds=0),
        ),
        device=device,
        model_client=model,
    )

    assert agent.run("inspect screen") == "done"
    assert device.observe_calls == 2
    assert len(model.requests) == 1
    error = next(event for event in agent.trajectory.events if event["type"] == "error")
    assert error["payload"]["error_code"] == "observation_failed"
    recovery = [event for event in agent.trajectory.events if event["type"] == "recovery"]
    assert recovery[-1]["payload"]["decision"]["strategy"] == "reobserve"


def test_adb_action_failure_is_not_blindly_replayed(tmp_path) -> None:
    device = FailingTapDevice()
    model = FakeModelClient(
        [
            ModelResponse(
                thinking="tap once",
                action='do(action="Tap", element=[500, 500])',
                raw_content='do(action="Tap", element=[500, 500])',
            ),
            ModelResponse(
                thinking="stop after structured failure",
                action='finish(message="stopped", success=False)',
                raw_content='finish(message="stopped", success=False)',
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
        device=device,
        model_client=model,
    )

    assert agent.run("tap target") == "stopped"
    assert device.tap_attempts == 1
    executions = [event for event in agent.trajectory.events if event["type"] == "execution"]
    assert executions[0]["payload"]["error_code"] == "action_execution_failed"
    recoveries = [event for event in agent.trajectory.events if event["type"] == "recovery"]
    outcome = next(event for event in recoveries if event["payload"]["stage"] == "outcome")
    assert outcome["payload"]["decision"]["strategy"] == "reobserve"
