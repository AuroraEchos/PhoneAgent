from __future__ import annotations

import copy
import tempfile
import unittest

from phoneagent.actions import do
from phoneagent.adb.screenshot import Screenshot
from phoneagent.agent import AgentConfig, PhoneAgent
from phoneagent.devices import ScreenObservation
from phoneagent.model import ModelConfig, ModelProtocolError, ModelResponse
from phoneagent.runtime import (
    AgentEvent,
    AgentPhase,
    AgentState,
    EventType,
    RecoveryConfig,
    RecoveryContext,
    RecoveryManager,
    RecoveryStrategy,
    StateTransitionError,
    TrajectoryRecorder,
)


class _FakeDevice:
    device_id = "fake-device"

    def observe(self) -> ScreenObservation:
        return ScreenObservation(
            screenshot=Screenshot(
                base64_data="eA==",
                width=100,
                height=200,
                display_width=100,
                display_height=200,
                available=True,
                is_blank=False,
            ),
            current_app="Launcher",
            current_package="com.example.launcher",
        )


class _FinishModel:
    def request(self, messages, *, print_stream=True):  # noqa: ANN001
        return ModelResponse(
            thinking="目标已经完成",
            action='finish(message="done", success=True)',
            raw_content='finish(message="done", success=True)',
        )


class _ProtocolThenFinishModel:
    def __init__(self, finish_reason: str | None = None) -> None:
        self.calls = 0
        self.messages: list[list[dict]] = []
        self.finish_reason = finish_reason

    def request(self, messages, *, print_stream=True):  # noqa: ANN001
        self.calls += 1
        self.messages.append(copy.deepcopy(messages))
        if self.calls == 1:
            raise ModelProtocolError(
                "Compatibility response included prose before the action",
                raw_content='先返回上一页 do(action="Back")',
                finish_reason=self.finish_reason,
            )
        return _FinishModel().request(messages, print_stream=print_stream)


class _InvalidArgumentsThenFinishModel:
    def __init__(self) -> None:
        self.calls = 0

    def request(self, messages, *, print_stream=True):  # noqa: ANN001
        del messages, print_stream
        self.calls += 1
        if self.calls == 1:
            raw = 'do(action="Back", unexpected="value")'
            return ModelResponse(thinking="", action=raw, raw_content=raw)
        return ModelResponse(
            thinking="",
            action='finish(message="done", success=True)',
            raw_content='finish(message="done", success=True)',
        )


class RuntimeCoreTests(unittest.TestCase):
    def test_state_has_single_phase_source(self) -> None:
        state = AgentState()
        transition = state.start("test")
        self.assertEqual(state.phase, AgentPhase.INITIALIZING)
        self.assertFalse(state.finished)
        self.assertEqual(transition["previous"], "idle")
        self.assertNotIn("step", transition)
        self.assertNotIn("timestamp", transition)
        self.assertNotIn("state_machine", state.to_dict())
        with self.assertRaises(StateTransitionError):
            state.transition(AgentPhase.EXECUTING)

        state.transition(AgentPhase.OBSERVING)
        finish_transition = state.finish(success=True, message="done")
        self.assertEqual(finish_transition["current"], "completed")
        self.assertTrue(state.finished)

        state.start("cancel test")
        cancel_transition = state.cancel(message="cancelled")
        self.assertEqual(cancel_transition["current"], "cancelled")
        self.assertFalse(state.success)

    def test_stagnation_prefers_application_content_signature(self) -> None:
        state = AgentState()
        state.update_observation(
            {"screenshot_sha256": "full-1", "content_sha256": "content"},
            step=1,
        )
        state.update_observation(
            {"screenshot_sha256": "full-2", "content_sha256": "content"},
            step=2,
        )

        self.assertFalse(state.last_observation["screen_changed_since_previous"])
        self.assertEqual(state.last_observation["screen_change_basis"], "content_sha256")
        self.assertEqual(state.stagnant_observation_count, 1)

    def test_recovery_retries_only_safe_actions(self) -> None:
        manager = RecoveryManager(RecoveryConfig())
        safe = manager.decide(
            RecoveryContext(
                error_code="verification_no_effect",
                message="no effect",
                action=do(action="Launch", app="微信"),
                consecutive_failures=1,
                repeated_action_count=1,
                current_app="Launcher",
            )
        )
        self.assertEqual(safe.strategy, RecoveryStrategy.RETRY_ACTION)

        manager.reset()
        risky = manager.decide(
            RecoveryContext(
                error_code="verification_no_effect",
                message="no effect",
                action=do(action="Tap", element=[500, 500], sensitive=True),
                consecutive_failures=1,
                repeated_action_count=1,
                current_app="微信",
            )
        )
        self.assertEqual(risky.strategy, RecoveryStrategy.REPLAN)

    def test_one_event_is_used_for_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recorder = TrajectoryRecorder(output_dir=tmp, task="test")
            event = AgentEvent(
                type=EventType.ACTION,
                message="action",
                payload={"action": "Back"},
                step=1,
            )
            recorder.add_event(event)
            saved = recorder.events[0]
            self.assertEqual(saved["timestamp"], event.timestamp)
            self.assertEqual(saved["step"], 1)
            self.assertEqual(saved["payload"], {"action": "Back"})

    def test_agent_runtime_smoke_with_injected_backends(self) -> None:
        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(
                save_trajectory=False,
                verbose=False,
                max_steps=2,
            ),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=_FinishModel(),  # type: ignore[arg-type]
        )
        self.assertEqual(agent.run("测试任务"), "done")
        self.assertTrue(agent.state.success)
        self.assertEqual(agent.state.phase, AgentPhase.COMPLETED)
        self.assertEqual(agent.step_count, 1)
        self.assertIsNone(agent.state.last_execution["command_success"])

    def test_finish_step_preserves_event_order_and_command_semantics(self) -> None:
        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(save_trajectory=False, verbose=False),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=_FinishModel(),  # type: ignore[arg-type]
        )

        self.assertEqual(agent.run("测试任务"), "done")

        events = agent.trajectory.events
        self.assertEqual(
            [event["type"] for event in events],
            [
                "phase_change",
                "start",
                "phase_change",
                "observation",
                "phase_change",
                "model_request",
                "model_response",
                "metrics",
                "action",
                "phase_change",
                "execution",
                "phase_change",
                "finish",
            ],
        )
        execution = next(event for event in events if event["type"] == "execution")
        self.assertIsNone(execution["payload"]["command_success"])
        self.assertEqual(execution["payload"]["action"]["_metadata"], "finish")
        self.assertEqual(events[-1]["payload"]["phase"], "completed")

    def test_event_callback_cannot_mutate_runtime_action_or_transition_state(self) -> None:
        def mutate_event(event: AgentEvent) -> None:
            if event.type is EventType.ACTION:
                event.payload["action"]["success"] = False

        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(save_trajectory=False, verbose=False),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=_FinishModel(),  # type: ignore[arg-type]
            event_callback=mutate_event,
        )

        self.assertEqual(agent.run("测试任务"), "done")
        self.assertTrue(agent.state.success)
        phase_events = [
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.PHASE_CHANGE.value
        ]
        self.assertTrue(all("step" in event for event in phase_events))
        self.assertTrue(all("step" not in event["payload"] for event in phase_events))
        self.assertTrue(all("timestamp" not in event["payload"] for event in phase_events))

    def test_model_protocol_error_uses_same_step_action_only_retry(self) -> None:
        model = _ProtocolThenFinishModel()
        agent = PhoneAgent(
            model_config=ModelConfig(max_tokens=256),
            agent_config=AgentConfig(
                save_trajectory=False,
                verbose=False,
                max_steps=3,
                recovery=RecoveryConfig(retry_delay_seconds=0),
            ),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=model,  # type: ignore[arg-type]
        )

        self.assertEqual(agent.run("测试任务"), "done")
        self.assertEqual(model.calls, 2)
        self.assertEqual(agent.step_count, 1)
        self.assertEqual(agent.state.recovery_count, 0)
        self.assertIn("PROTOCOL RETRY", str(model.messages[1][-1]["content"]))

        response_events = [
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.MODEL_RESPONSE.value
        ]
        self.assertEqual(
            response_events[0]["payload"]["raw_content"],
            '先返回上一页 do(action="Back")',
        )
        self.assertIn("protocol_error", response_events[0]["payload"])
        retry_events = [
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.PROTOCOL_RETRY.value
        ]
        self.assertEqual(len(retry_events), 1)
        self.assertFalse(retry_events[0]["payload"]["command_dispatched"])
        self.assertEqual(retry_events[0]["payload"]["max_tokens"], 256)
        self.assertFalse(
            any(event["type"] == EventType.ERROR.value for event in agent.trajectory.events)
        )

    def test_truncated_protocol_error_is_reported_separately(self) -> None:
        model = _ProtocolThenFinishModel(finish_reason="length")
        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(
                save_trajectory=False,
                verbose=False,
                max_steps=3,
                recovery=RecoveryConfig(retry_delay_seconds=0),
            ),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=model,  # type: ignore[arg-type]
        )

        self.assertEqual(agent.run("测试任务"), "done")
        response_events = [
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.MODEL_RESPONSE.value
        ]
        self.assertEqual(response_events[0]["payload"]["finish_reason"], "length")
        self.assertTrue(response_events[0]["payload"]["truncated"])
        retry_events = [
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.PROTOCOL_RETRY.value
        ]
        self.assertEqual(len(retry_events), 1)
        self.assertFalse(
            any(event["type"] == EventType.ERROR.value for event in agent.trajectory.events)
        )

    def test_exhausted_protocol_retry_enters_existing_strict_recovery(self) -> None:
        model = _ProtocolThenFinishModel()
        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(
                save_trajectory=False,
                verbose=False,
                max_steps=3,
                protocol_retries=0,
                recovery=RecoveryConfig(retry_delay_seconds=0),
            ),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=model,  # type: ignore[arg-type]
        )

        self.assertEqual(agent.run("测试任务"), "done")
        self.assertEqual(agent.step_count, 2)
        self.assertIn("STRICT ACTION RECOVERY", str(model.messages[1][-1]["content"]))
        error = next(
            event for event in agent.trajectory.events if event["type"] == EventType.ERROR.value
        )
        self.assertEqual(error["payload"]["error_code"], "model_protocol_error")

    def test_invalid_inner_action_schema_uses_same_step_retry(self) -> None:
        model = _InvalidArgumentsThenFinishModel()
        agent = PhoneAgent(
            model_config=ModelConfig(),
            agent_config=AgentConfig(save_trajectory=False, verbose=False, max_steps=1),
            device=_FakeDevice(),  # type: ignore[arg-type]
            model_client=model,  # type: ignore[arg-type]
        )

        self.assertEqual(agent.run("测试任务"), "done")
        self.assertEqual(model.calls, 2)
        self.assertEqual(agent.step_count, 1)
        retry = next(
            event
            for event in agent.trajectory.events
            if event["type"] == EventType.PROTOCOL_RETRY.value
        )
        self.assertEqual(retry["payload"]["protocol_error_code"], "invalid_action_arguments")


if __name__ == "__main__":
    unittest.main()
