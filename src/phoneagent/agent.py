"""Android-only PhoneAgent runtime."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from phoneagent.actions import ActionHandler, ActionParseError, ActionResult, do, finish, parse_action
from phoneagent.apps import (
    AppCatalogConfig,
    AppDiscoveryConfig,
    AppLauncherConfig,
    AppResolution,
    PureLaunchIntent,
    extract_pure_launch_intent,
)
from phoneagent.config import get_messages, get_system_prompt
from phoneagent.devices import AndroidDevice, ScreenObservation
from phoneagent.model import MessageBuilder, ModelClient, ModelConfig
from phoneagent.runtime import (
    ActionVerifier,
    AgentEvent,
    AgentPhase,
    AgentState,
    EventType,
    RecoveryConfig,
    RecoveryContext,
    RecoveryManager,
    RecoveryOutcome,
    RecoveryStrategy,
    TrajectoryRecorder,
    VerificationConfig,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentConfig:
    """Configuration for the Android agent loop."""

    max_steps: int = 100
    max_runtime_seconds: float = 900.0
    device_id: str | None = None
    system_prompt: str | None = None
    verbose: bool = True
    context_turns: int = 12
    max_consecutive_failures: int = 3
    max_repeated_actions: int = 3
    observation_retries: int = 2
    observation_retry_delay: float = 0.5
    trajectory_dir: str = "runs"
    save_trajectory: bool = True
    allow_fallback_screenshot: bool = False
    app_awareness_enabled: bool = True
    inject_app_context: bool = True
    deterministic_pure_launch_enabled: bool = True
    strict_action_recovery_enabled: bool = True
    max_app_context_chars: int = 6000
    app_catalog: AppCatalogConfig = field(default_factory=AppCatalogConfig)
    app_discovery: AppDiscoveryConfig = field(default_factory=AppDiscoveryConfig)
    app_launcher: AppLauncherConfig = field(default_factory=AppLauncherConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    recovery: RecoveryConfig = field(default_factory=RecoveryConfig)

    def __post_init__(self) -> None:
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt()
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.max_runtime_seconds < 0:
            raise ValueError("max_runtime_seconds cannot be negative")
        if self.context_turns < 1:
            raise ValueError("context_turns must be at least 1")
        if self.max_consecutive_failures < 0:
            raise ValueError("max_consecutive_failures cannot be negative")
        if self.max_repeated_actions < 0:
            raise ValueError("max_repeated_actions cannot be negative")
        if self.observation_retries < 0:
            raise ValueError("observation_retries cannot be negative")
        if self.observation_retry_delay < 0:
            raise ValueError("observation_retry_delay cannot be negative")
        if self.max_app_context_chars < 256:
            raise ValueError("max_app_context_chars must be at least 256")


@dataclass(slots=True)
class StepResult:
    """Result of a single observe-plan-execute-verify step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None
    raw_model_output: str | None = None
    error_code: str | None = None
    command_success: bool | None = None
    verification: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None
    phase: str | None = None


@dataclass(slots=True)
class _RecoveryExecution:
    outcome: RecoveryOutcome
    action_recovered: bool = False
    verification: VerificationResult | None = None
    observation: ScreenObservation | None = None


EventCallback = Callable[[AgentEvent], None]


class PhoneAgent:
    """Vision-language Android automation agent.

    Runtime flow:
        observe -> plan -> execute -> verify -> recover/replan -> repeat.
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
        event_callback: EventCallback | None = None,
        *,
        device: AndroidDevice | None = None,
        model_client: ModelClient | None = None,
        api_callback: Callable[[str], str | None] | None = None,
        note_callback: Callable[[str], None] | None = None,
    ):
        self.agent_config = agent_config or AgentConfig()
        self.model_config = model_config or ModelConfig()
        self.device = device or AndroidDevice(
            device_id=self.agent_config.device_id,
            allow_fallback_screenshot=self.agent_config.allow_fallback_screenshot,
            app_catalog_config=self.agent_config.app_catalog,
            app_discovery_config=self.agent_config.app_discovery,
            app_launcher_config=self.agent_config.app_launcher,
        )
        self.app_catalog = (
            getattr(self.device, "app_catalog", None)
            if self.agent_config.app_awareness_enabled
            else None
        )
        self._device_app_context: dict[str, Any] = {}
        self.model_client = model_client or ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            api_callback=api_callback,
            note_callback=note_callback,
        )
        self.verifier = ActionVerifier(self.agent_config.verification)
        self.recovery_manager = RecoveryManager(self.agent_config.recovery)
        self.event_callback = event_callback
        self.state = AgentState()
        self.trajectory = TrajectoryRecorder(output_dir=self.agent_config.trajectory_dir)
        self.last_trajectory_path: str | None = None
        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._pending_observation: ScreenObservation | None = None
        self._pure_launch_intent: PureLaunchIntent | None = None
        self._pure_launch_resolution: AppResolution | None = None
        self._direct_route_attempted = False
        self._strict_action_recovery: str | None = None

    def run(self, task: str) -> str:
        """Run until completion, terminal failure, or configured limits."""
        if not str(task or "").strip():
            raise ValueError("task cannot be empty")
        self._start_run(str(task).strip())
        result: StepResult | None = None

        try:
            while self._step_count < self.agent_config.max_steps:
                if self._runtime_limit_reached():
                    result = StepResult(
                        success=False,
                        finished=True,
                        action=finish(message="Maximum runtime reached", success=False),
                        thinking="",
                        message="Maximum runtime reached",
                        error_code="max_runtime_reached",
                        phase=self.state.phase.value,
                    )
                    break
                is_first = not any(
                    message.get("role") == "system" for message in self._context
                )
                result = self._execute_step(
                    user_prompt=task if is_first else None,
                    is_first=is_first,
                )
                if result.finished:
                    break
        except KeyboardInterrupt:
            result = StepResult(
                success=False,
                finished=True,
                action=finish(message="Task interrupted by user", success=False),
                thinking="",
                message="Task interrupted by user",
                error_code="interrupted",
                phase=self.state.phase.value,
            )

        if result is None or not result.finished:
            result = StepResult(
                success=False,
                finished=True,
                action=finish(message="Maximum step limit reached", success=False),
                thinking="",
                message="Maximum step limit reached",
                error_code="max_steps_reached",
                phase=self.state.phase.value,
            )
        self._finalize_run(result)
        return result.message or ("Task completed" if result.success else "Task failed")

    def step(self, task: str | None = None) -> StepResult:
        """Execute exactly one observe-plan-execute-verify step."""
        if self.state.finished:
            if not task:
                raise ValueError("task is required after a finished run")
            self._start_run(task)
        elif self.state.started_at is None:
            if not task:
                raise ValueError("task is required for the first step")
            self._start_run(task)

        is_first = not any(
            message.get("role") == "system" for message in self._context
        )
        result = self._execute_step(
            (task or self.state.goal) if is_first else None,
            is_first=is_first,
        )
        if result.finished:
            self._finalize_run(result)
        return result

    def reset(self) -> None:
        """Clear context, counters, state machine and trajectory state."""
        self._context.clear()
        self._step_count = 0
        self._pending_observation = None
        self._device_app_context = {}
        self._pure_launch_intent = None
        self._pure_launch_resolution = None
        self._direct_route_attempted = False
        self._strict_action_recovery = None
        self.state.reset()
        self.recovery_manager.reset()
        self.trajectory = TrajectoryRecorder(output_dir=self.agent_config.trajectory_dir)
        self.last_trajectory_path = None

    def _execute_step(
        self,
        user_prompt: str | None = None,
        is_first: bool = False,
    ) -> StepResult:
        self._step_count += 1
        self.state.begin_step(self._step_count)
        msgs = get_messages()
        self._transition(AgentPhase.OBSERVING, "Acquire current device state")

        try:
            observation = self._next_observation()
        except Exception as exc:
            return self._handle_runtime_failure(
                message=f"Observation failed: {exc}",
                error_code="observation_failed",
                thinking="",
                raw_model_output=None,
                action=None,
            )

        if not observation.screenshot.available:
            return self._handle_runtime_failure(
                message=observation.screenshot.error or "Screenshot unavailable",
                error_code="screenshot_unavailable",
                thinking="",
                raw_model_output=None,
                action=None,
            )
        if observation.screenshot.is_blank:
            return self._handle_runtime_failure(
                message=(
                    "The captured screen is blank or protected. PhoneAgent will not "
                    "guess coordinates on an unobservable screen."
                ),
                error_code="protected_or_blank_screen",
                thinking="",
                raw_model_output=None,
                action=None,
            )

        deterministic_result = self._try_deterministic_pure_launch(observation)
        if deterministic_result is not None:
            return deterministic_result

        self._append_user_message(observation, user_prompt=user_prompt, is_first=is_first)
        self._trim_context()
        self._transition(AgentPhase.PLANNING, "Request one constrained model action")

        try:
            if self.agent_config.verbose:
                print("\n" + "=" * 50)
                print(f"{msgs['thinking']}:")
                print("-" * 50)
            self._record_event(
                EventType.MODEL_REQUEST,
                "Requesting model",
                {
                    "step": self._step_count,
                    "message_count": len(self._context),
                    "current_app": observation.current_app,
                    "phase": self.state.phase.value,
                },
            )
            response = self.model_client.request(
                self._context,
                print_stream=self.agent_config.verbose,
            )
        except Exception as exc:
            logger.exception("Model request failed: %s", exc)
            if self._context and self._context[-1].get("role") == "user":
                # The request never produced an assistant turn. Remove the current
                # user message so the next retry keeps a valid role sequence and
                # attaches a fresh screenshot. The system prompt remains in place.
                self._context.pop()
            return self._handle_runtime_failure(
                message=f"Model request failed: {exc}",
                error_code="model_request_failed",
                thinking="",
                raw_model_output=None,
                action=None,
            )

        metrics = {
            "time_to_first_token": response.time_to_first_token,
            "time_to_thinking_end": response.time_to_thinking_end,
            "total_time": response.total_time,
            "attempts": response.attempts,
            "finish_reason": response.finish_reason,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "truncated": response.truncated,
        }
        self.state.update_model_response(
            thinking=response.thinking,
            raw_content=response.raw_content,
        )
        self._record_event(
            EventType.MODEL_RESPONSE,
            "Model response received",
            {
                "thinking": response.thinking,
                "action": response.action,
                "raw_content": response.raw_content,
                "metrics": metrics,
                "step": self._step_count,
            },
        )
        self._record_event(
            EventType.METRICS,
            "Model timing captured",
            {"metrics": metrics, "step": self._step_count},
        )

        try:
            action = parse_action(response.action)
        except ActionParseError as exc:
            error_code = (
                "model_output_truncated" if response.truncated else "action_parse_error"
            )
            message = (
                "Model output was truncated before a valid action could be completed "
                f"(finish_reason={response.finish_reason}): {exc}"
                if response.truncated
                else f"Model action parse error: {exc}"
            )
            if self.agent_config.verbose:
                preview = response.action[:2000]
                suffix = "\n...[truncated preview]" if len(response.action) > len(preview) else ""
                print(f"\n{message}\nRaw action preview: {preview}{suffix}")
            self._prepare_strict_action_recovery(message)
            return self._handle_runtime_failure(
                message=message,
                error_code=error_code,
                thinking=response.thinking,
                raw_model_output=response.raw_content,
                action=None,
            )

        signature = self._action_signature(action)
        self.state.update_action(action, step=self._step_count, signature=signature)
        self._record_event(
            EventType.ACTION,
            "Parsed action",
            {
                "action": action,
                "thinking": response.thinking,
                "step": self._step_count,
                "repeated_action_count": self.state.repeated_action_count,
            },
        )
        if self.agent_config.verbose:
            print("-" * 50)
            print(f"{msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])
        self._context.append(
            MessageBuilder.create_assistant_message(response.to_assistant_message_content())
        )
        self._transition(AgentPhase.EXECUTING, "Execute validated Android action")

        if self._should_block_repeated_action(action):
            execution = ActionResult(
                success=False,
                should_finish=False,
                message=(
                    "Blocked an identical action because the screen remained unchanged. "
                    "Choose a different target or strategy."
                ),
                error_code="repeated_action_blocked",
                metadata={
                    "repeated_action_count": self.state.repeated_action_count,
                    "stagnant_observation_count": self.state.stagnant_observation_count,
                },
            )
        else:
            execution = self.action_handler.execute(
                action,
                int(observation.screenshot.display_width or observation.screenshot.width),
                int(observation.screenshot.display_height or observation.screenshot.height),
            )

        self._record_command_execution(action, execution)

        if action.get("_metadata") == "finish" or execution.should_finish:
            self.state.update_execution(
                success=execution.success,
                command_success=execution.success,
                should_finish=True,
                message=execution.message,
                action=action,
                error_code=execution.error_code,
                metadata=execution.metadata,
            )
            message = execution.message or str(action.get("message") or "") or None
            return StepResult(
                success=execution.success,
                finished=True,
                action=action,
                thinking=response.thinking,
                message=message,
                raw_model_output=response.raw_content,
                error_code=execution.error_code,
                command_success=execution.success,
                phase=self.state.phase.value,
            )

        verification = self._verify_action(action, execution, observation)
        recovery_execution: _RecoveryExecution | None = None
        overall_success = verification.passed
        final_verification = verification
        error_code = verification.error_code or execution.error_code
        message = verification.message if not verification.passed else execution.message

        if not verification.passed:
            recovery_execution = self._perform_recovery(
                action=action,
                execution=execution,
                verification=verification,
            )
            if recovery_execution.verification is not None:
                final_verification = recovery_execution.verification
            if recovery_execution.action_recovered:
                overall_success = True
                error_code = None
                message = recovery_execution.outcome.message
            elif recovery_execution.outcome.decision.terminal:
                message = recovery_execution.outcome.message
                error_code = recovery_execution.outcome.error_code or error_code

        if overall_success:
            self.recovery_manager.mark_success()

        recovery_payload = (
            recovery_execution.outcome.to_dict() if recovery_execution is not None else None
        )
        self.state.update_execution(
            success=overall_success,
            command_success=execution.success,
            should_finish=False,
            message=message,
            action=action,
            error_code=error_code,
            metadata=execution.metadata,
            verification=final_verification.to_dict(),
            recovery=recovery_payload,
        )
        if recovery_payload is not None:
            self.state.update_recovery(recovery_payload)

        finished = bool(
            recovery_execution
            and recovery_execution.outcome.decision.terminal
        ) or self._failure_limit_reached()
        if finished and not self.state.phase.terminal:
            self._transition(AgentPhase.FAILED, "Recovery or failure budget exhausted")
        elif not self.state.phase.terminal:
            self._transition(AgentPhase.OBSERVING, "Continue with verified/recovered state")

        return StepResult(
            success=overall_success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=message,
            raw_model_output=response.raw_content,
            error_code=error_code,
            command_success=execution.success,
            verification=final_verification.to_dict(),
            recovery=recovery_payload,
            phase=self.state.phase.value,
        )

    def _try_deterministic_pure_launch(
        self,
        observation: ScreenObservation,
    ) -> StepResult | None:
        """Execute a high-confidence pure app launch without calling the VLM."""
        if (
            not self.agent_config.deterministic_pure_launch_enabled
            or self._direct_route_attempted
            or self._pure_launch_intent is None
            or self._pure_launch_resolution is None
            or self._pure_launch_resolution.matched_app is None
            or not callable(getattr(self.device, "launch_app_resolved", None))
        ):
            return None

        self._direct_route_attempted = True
        app = self._pure_launch_resolution.matched_app
        action = do(action="Launch", app=app.package_name)
        thinking = (
            "Runtime deterministically resolved the pure launch task to "
            f"{app.display_name} ({app.package_name})."
        )

        self._transition(
            AgentPhase.PLANNING,
            "Resolve pure application launch deterministically",
            metadata={
                "route": "deterministic_pure_launch",
                "query": self._pure_launch_intent.query,
                "package_name": app.package_name,
                "confidence": self._pure_launch_resolution.confidence,
            },
        )
        signature = self._action_signature(action)
        self.state.update_action(action, step=self._step_count, signature=signature)
        self._record_event(
            EventType.ACTION,
            "Deterministic pure-launch action",
            {
                "action": action,
                "thinking": thinking,
                "step": self._step_count,
                "route": "deterministic_pure_launch",
                "resolution": self._pure_launch_resolution.to_dict(),
            },
        )
        if self.agent_config.verbose:
            print("\n" + "=" * 50)
            print("Deterministic Route:")
            print("-" * 50)
            print(thinking)
            print("-" * 50)
            print("Action:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        self._transition(AgentPhase.EXECUTING, "Execute deterministic launch action")
        width = int(observation.screenshot.display_width or observation.screenshot.width)
        height = int(observation.screenshot.display_height or observation.screenshot.height)
        execution = self.action_handler.execute(action, width, height)
        self._record_command_execution(action, execution)
        verification = self._verify_action(action, execution, observation)

        recovery_execution: _RecoveryExecution | None = None
        final_verification = verification
        overall_success = verification.passed
        error_code = verification.error_code or execution.error_code
        message = verification.message if not verification.passed else execution.message

        if not verification.passed:
            recovery_execution = self._perform_recovery(
                action=action,
                execution=execution,
                verification=verification,
            )
            if recovery_execution.verification is not None:
                final_verification = recovery_execution.verification
            if recovery_execution.action_recovered:
                overall_success = True
                error_code = None
                message = recovery_execution.outcome.message
            elif recovery_execution.outcome.decision.terminal:
                error_code = recovery_execution.outcome.error_code or error_code
                message = recovery_execution.outcome.message

        if overall_success:
            self.recovery_manager.mark_success()

        recovery_payload = (
            recovery_execution.outcome.to_dict() if recovery_execution is not None else None
        )
        if final_verification.policy == "verification_disabled":
            # Diagnostic mode accepts the launch command without claiming that
            # the foreground application was independently verified.
            completed = bool(execution.success and final_verification.passed)
        else:
            completed = bool(
                overall_success
                and final_verification.passed
                and final_verification.semantic_effect_verified is True
            )
        if completed:
            message = f"Opened {app.display_name} ({app.package_name})"

        self.state.update_execution(
            success=completed,
            command_success=execution.success,
            should_finish=completed,
            message=message,
            action=action,
            error_code=None if completed else error_code,
            metadata={
                **execution.metadata,
                "route": "deterministic_pure_launch",
            },
            verification=final_verification.to_dict(),
            recovery=recovery_payload,
        )
        if recovery_payload is not None:
            self.state.update_recovery(recovery_payload)

        terminal_failure = bool(
            recovery_execution and recovery_execution.outcome.decision.terminal
        ) or self._failure_limit_reached()
        if not completed and not terminal_failure and not self.state.phase.terminal:
            self._transition(
                AgentPhase.OBSERVING,
                "Deterministic launch did not complete; continue with model replanning",
            )
        elif terminal_failure and not self.state.phase.terminal:
            self._transition(AgentPhase.FAILED, "Deterministic launch recovery exhausted")

        return StepResult(
            success=completed,
            finished=completed or terminal_failure,
            action=action,
            thinking=thinking,
            message=message,
            raw_model_output=None,
            error_code=None if completed else error_code,
            command_success=execution.success,
            verification=final_verification.to_dict(),
            recovery=recovery_payload,
            phase=self.state.phase.value,
        )

    def _verify_action(
        self,
        action: dict[str, Any],
        execution: ActionResult,
        before: ScreenObservation,
    ) -> VerificationResult:
        if not execution.success:
            result = self.verifier.verify(
                action=action,
                execution=execution,
                before=before,
                after=None,
            )
            self._record_verification(action, result)
            return result

        self._transition(AgentPhase.VERIFYING, "Verify action outcome")
        action_name = str(action.get("action", ""))
        needs_observation = action_name not in {"Note", "Call_API"}
        after: ScreenObservation | None = None
        if needs_observation:
            if self.agent_config.verification.settle_delay_seconds > 0:
                time.sleep(self.agent_config.verification.settle_delay_seconds)
            try:
                after = self._observe_with_retries(
                    retries=self.agent_config.verification.observation_retries,
                    retry_delay=self.agent_config.verification.observation_retry_delay,
                )
                if not after.screenshot.available:
                    raise RuntimeError(after.screenshot.error or "Screenshot unavailable")
                if after.screenshot.is_blank:
                    result = self.verifier.observation_failure(
                        action=action,
                        execution=execution,
                        message="Post-action screen is blank or protected",
                        error_code="protected_or_blank_screen",
                    )
                    self._record_verification(action, result)
                    return result
                self._record_observation(after, source="post_action_verification")
                self._pending_observation = after
            except Exception as exc:
                result = self.verifier.observation_failure(
                    action=action,
                    execution=execution,
                    message=f"Post-action observation failed: {exc}",
                )
                self._record_verification(action, result)
                return result

        result = self.verifier.verify(
            action=action,
            execution=execution,
            before=before,
            after=after,
        )
        self._record_verification(action, result)
        return result

    def _perform_recovery(
        self,
        *,
        action: dict[str, Any] | None,
        execution: ActionResult,
        verification: VerificationResult,
    ) -> _RecoveryExecution:
        self._transition(AgentPhase.RECOVERING, "Apply bounded recovery policy")
        decision = self.recovery_manager.decide(
            RecoveryContext(
                error_code=verification.error_code or execution.error_code or "unknown_failure",
                message=verification.message or execution.message or "Action failed",
                action=action,
                consecutive_failures=self.state.consecutive_failures + 1,
                repeated_action_count=self.state.repeated_action_count,
                current_app=self.state.current_app,
                target_app=self.state.target_app,
                verification=verification,
            )
        )
        self._record_event(
            EventType.RECOVERY,
            decision.reason,
            {**decision.to_dict(), "step": self._step_count, "stage": "decision"},
        )

        if decision.strategy == RecoveryStrategy.ABORT:
            outcome = RecoveryOutcome(
                decision=decision,
                success=False,
                message=decision.reason,
                error_code="recovery_aborted",
            )
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

        if decision.strategy == RecoveryStrategy.REPLAN:
            outcome = RecoveryOutcome(
                decision=decision,
                success=True,
                message="Recovery selected model replanning without replaying the action",
            )
            self._transition(AgentPhase.OBSERVING, "Recovery complete; replan")
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

        if decision.strategy == RecoveryStrategy.REOBSERVE:
            return self._recover_by_observation(decision)

        if decision.strategy in {RecoveryStrategy.RETRY_ACTION, RecoveryStrategy.RELAUNCH}:
            retry_action = action
            if decision.strategy == RecoveryStrategy.RELAUNCH:
                target = str((action or {}).get("app") or self.state.target_app).strip()
                retry_action = do(action="Launch", app=target)
            return self._recover_by_action_retry(decision, retry_action)

        if decision.strategy in {RecoveryStrategy.BACKTRACK, RecoveryStrategy.HOME_RESET}:
            try:
                if decision.strategy == RecoveryStrategy.BACKTRACK:
                    self.device.back()
                    command = "Back"
                else:
                    self.device.home()
                    command = "Home"
                observation = self._observe_with_retries()
                self._record_observation(observation, source=f"recovery_{decision.strategy.value}")
                self._pending_observation = observation
                outcome = RecoveryOutcome(
                    decision=decision,
                    success=True,
                    message=f"Recovery command {command} completed",
                )
                self._transition(AgentPhase.OBSERVING, "Navigation recovery complete")
                self._record_recovery_outcome(outcome)
                return _RecoveryExecution(outcome=outcome, observation=observation)
            except Exception as exc:
                outcome = RecoveryOutcome(
                    decision=decision,
                    success=False,
                    message=f"Navigation recovery failed: {exc}",
                    error_code="recovery_navigation_failed",
                )
                self._transition(
                    AgentPhase.OBSERVING,
                    "Navigation recovery failed; retry normal observation",
                )
                self._record_recovery_outcome(outcome)
                return _RecoveryExecution(outcome=outcome)

        if decision.strategy == RecoveryStrategy.TAKEOVER:
            try:
                self._transition(AgentPhase.WAITING_USER, "Manual takeover required")
                takeover = self.action_handler.execute(
                    do(action="Take_over", message=decision.reason),
                    1,
                    1,
                )
                if not takeover.success:
                    raise RuntimeError(takeover.message or "Manual takeover failed")
                observation = self._observe_with_retries()
                self._record_observation(observation, source="recovery_takeover")
                self._pending_observation = observation
                outcome = RecoveryOutcome(
                    decision=decision,
                    success=True,
                    message="Manual takeover completed and the screen was reobserved",
                )
                self._transition(AgentPhase.OBSERVING, "Manual takeover complete")
                self._record_recovery_outcome(outcome)
                return _RecoveryExecution(outcome=outcome, observation=observation)
            except Exception as exc:
                decision.terminal = True
                outcome = RecoveryOutcome(
                    decision=decision,
                    success=False,
                    message=f"Manual takeover recovery failed: {exc}",
                    error_code="recovery_takeover_failed",
                )
                self._transition(AgentPhase.FAILED, "Manual takeover failed")
                self._record_recovery_outcome(outcome)
                return _RecoveryExecution(outcome=outcome)

        decision.terminal = True
        outcome = RecoveryOutcome(
            decision=decision,
            success=False,
            message="No executable recovery strategy was selected",
            error_code="recovery_strategy_unhandled",
        )
        self._transition(AgentPhase.FAILED, "Recovery strategy was unhandled")
        self._record_recovery_outcome(outcome)
        return _RecoveryExecution(outcome=outcome)

    def _recover_by_observation(self, decision) -> _RecoveryExecution:
        if self.agent_config.recovery.retry_delay_seconds > 0:
            time.sleep(self.agent_config.recovery.retry_delay_seconds)
        try:
            observation = self._observe_with_retries()
            if observation.screenshot.is_blank:
                raise RuntimeError("Recovered observation is blank or protected")
            self._record_observation(observation, source="recovery_reobserve")
            self._pending_observation = observation
            outcome = RecoveryOutcome(
                decision=decision,
                success=True,
                message="Fresh observation acquired for replanning",
            )
            self._transition(AgentPhase.OBSERVING, "Fresh observation acquired")
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome, observation=observation)
        except Exception as exc:
            outcome = RecoveryOutcome(
                decision=decision,
                success=False,
                message=f"Reobservation recovery failed: {exc}",
                error_code="recovery_reobserve_failed",
            )
            self._transition(
                AgentPhase.OBSERVING,
                "Reobservation failed; retain recovery budget for the next step",
            )
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

    def _recover_by_action_retry(
        self,
        decision,
        action: dict[str, Any] | None,
    ) -> _RecoveryExecution:
        if not action:
            decision.terminal = True
            outcome = RecoveryOutcome(
                decision=decision,
                success=False,
                message="Recovery retry has no action",
                error_code="recovery_missing_action",
            )
            self._transition(AgentPhase.FAILED, "Recovery action missing")
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

        if self.agent_config.recovery.retry_delay_seconds > 0:
            time.sleep(self.agent_config.recovery.retry_delay_seconds)
        before = self._pending_observation or self._observation_from_state()
        self._transition(AgentPhase.EXECUTING, "Retry bounded safe action")
        width = int(before.screenshot.display_width or before.screenshot.width)
        height = int(before.screenshot.display_height or before.screenshot.height)
        retry_execution = self.action_handler.execute(action, width, height)
        self._record_command_execution(action, retry_execution, recovery=True)
        if not retry_execution.success:
            self._transition(AgentPhase.RECOVERING, "Recovery action command failed")
            outcome = RecoveryOutcome(
                decision=decision,
                success=False,
                message=retry_execution.message or "Recovery action command failed",
                error_code=retry_execution.error_code or "recovery_action_failed",
            )
            self._transition(AgentPhase.OBSERVING, "Return control to model after failed retry")
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

        retry_verification = self._verify_action(action, retry_execution, before)
        recovered = retry_verification.passed
        outcome = RecoveryOutcome(
            decision=decision,
            success=recovered,
            message=(
                "Original action recovered after bounded retry"
                if recovered
                else f"Recovery retry did not verify: {retry_verification.message}"
            ),
            error_code=None if recovered else retry_verification.error_code,
            metadata={"verification": retry_verification.to_dict()},
        )
        if not self.state.phase.terminal:
            self._transition(AgentPhase.OBSERVING, "Bounded action retry complete")
        self._record_recovery_outcome(outcome)
        return _RecoveryExecution(
            outcome=outcome,
            action_recovered=recovered,
            verification=retry_verification,
            observation=self._pending_observation,
        )

    def _handle_runtime_failure(
        self,
        *,
        message: str,
        error_code: str,
        thinking: str,
        raw_model_output: str | None,
        action: dict[str, Any] | None,
    ) -> StepResult:
        logger.warning("Runtime failure [%s]: %s", error_code, message)
        execution = ActionResult(
            success=False,
            should_finish=False,
            message=message,
            error_code=error_code,
        )
        verification = VerificationResult(
            status=VerificationStatus.FAILED,
            policy="runtime_precondition",
            message=message,
            command_success=False,
            observable_effect_verified=False,
            semantic_effect_verified=False,
            error_code=error_code,
        )
        self._record_event(
            EventType.ERROR,
            message,
            {"error_code": error_code, "step": self._step_count},
        )
        recovery = self._perform_recovery(
            action=action,
            execution=execution,
            verification=verification,
        )
        recovery_payload = recovery.outcome.to_dict()
        self.state.update_execution(
            success=False,
            command_success=False,
            should_finish=recovery.outcome.decision.terminal,
            message=message,
            action=action,
            error_code=error_code,
            verification=verification.to_dict(),
            recovery=recovery_payload,
        )
        self.state.update_recovery(recovery_payload)
        finished = recovery.outcome.decision.terminal or self._failure_limit_reached()
        if finished and not self.state.phase.terminal:
            self._transition(AgentPhase.FAILED, "Runtime failure budget exhausted")
        return StepResult(
            success=False,
            finished=finished,
            action=action,
            thinking=thinking,
            message=message,
            raw_model_output=raw_model_output,
            error_code=error_code,
            command_success=False,
            verification=verification.to_dict(),
            recovery=recovery_payload,
            phase=self.state.phase.value,
        )

    def _next_observation(self) -> ScreenObservation:
        if self._pending_observation is not None:
            observation = self._pending_observation
            self._pending_observation = None
            self._record_event(
                EventType.OBSERVATION,
                "Reusing verified post-action observation",
                {
                    **observation.to_screen_info(),
                    "current_app": observation.current_app,
                    "step": self._step_count,
                    "source": "verification_cache",
                    "cached": True,
                },
            )
            return observation
        observation = self._observe_with_retries()
        self._record_observation(observation, source="step_observation")
        return observation

    def _observe_with_retries(
        self,
        *,
        retries: int | None = None,
        retry_delay: float | None = None,
    ) -> ScreenObservation:
        retries = self.agent_config.observation_retries if retries is None else retries
        retry_delay = (
            self.agent_config.observation_retry_delay
            if retry_delay is None
            else retry_delay
        )
        attempts = retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self.device.observe()
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                time.sleep(retry_delay * attempt)
        assert last_error is not None
        raise last_error

    def _append_user_message(
        self,
        observation: ScreenObservation,
        *,
        user_prompt: str | None,
        is_first: bool,
    ) -> None:
        screen_payload = {
            **observation.to_screen_info(),
            "current_app": observation.current_app,
            "phase": self.state.phase.value,
            "stagnant_observation_count": self.state.stagnant_observation_count,
        }
        screen_info = MessageBuilder.build_screen_info(**screen_payload)
        sections: list[str] = []
        if is_first:
            assert self.agent_config.system_prompt is not None
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )
        goal = user_prompt or self.state.goal
        if goal:
            sections.append(f"** User Goal **\n{goal}")
        if self._strict_action_recovery:
            sections.append(
                "** STRICT ACTION RECOVERY **\n" + self._strict_action_recovery
            )
            self._strict_action_recovery = None
        if not is_first:
            previous_execution = self._build_previous_execution_info()
            if previous_execution:
                sections.append(previous_execution)
        if self.agent_config.inject_app_context and self._device_app_context:
            sections.append(
                "** Device App Context **\n"
                + self._serialize_app_context(self._device_app_context)
            )
        if self.action_handler.notes:
            sections.append(
                "** Saved Notes **\n"
                + json.dumps(
                    self.action_handler.notes[-20:],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        sections.append(f"** Runtime Phase **\n{self.state.phase.value}")
        sections.append(f"** Screen Info **\n{screen_info}")
        self._context.append(
            MessageBuilder.create_user_message(
                text="\n\n".join(sections),
                image_base64=observation.screenshot.base64_data,
                image_mime_type=observation.screenshot.mime_type,
            )
        )

    def _serialize_app_context(self, context: dict[str, Any]) -> str:
        """Serialize model-facing app context with a hard character budget."""
        text = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(text) <= self.agent_config.max_app_context_chars:
            return text
        minimal = {
            "catalog_available": context.get("catalog_available"),
            "installed_launchable_count": context.get("installed_launchable_count"),
            "likely_goal_apps": context.get("likely_goal_apps", [])[:1],
            "context_policy": "hard_truncated_to_primary_candidate",
            "launch_policy": context.get("launch_policy"),
        }
        compact = json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))
        if len(compact) <= self.agent_config.max_app_context_chars:
            return compact
        primary = self._primary_app_candidate() or {}
        tiny = {
            "catalog_available": context.get("catalog_available"),
            "installed_launchable_count": context.get("installed_launchable_count"),
            "primary_candidate": {
                "label": primary.get("label"),
                "package_name": primary.get("package_name"),
            },
            "context_policy": "minimal_valid_json",
        }
        return json.dumps(tiny, ensure_ascii=False, separators=(",", ":"))

    def _prepare_strict_action_recovery(self, reason: str) -> None:
        """Discard a malformed turn and prepare one compact protocol retry."""
        if self._context and self._context[-1].get("role") == "user":
            self._context.pop()
        self._compact_context_for_protocol_recovery()
        if not self.agent_config.strict_action_recovery_enabled:
            return
        candidate = self._primary_app_candidate()
        candidate_text = ""
        if candidate:
            candidate_text = (
                "\nResolved app candidate:\n"
                f"- label: {candidate.get('label', '')}\n"
                f"- package: {candidate.get('package_name', '')}\n"
            )
        self._strict_action_recovery = (
            f"Previous model output was unusable: {reason}.\n"
            "Do not repeat prior reasoning or enumerate applications. "
            "Return exactly one valid action inside <answer>...</answer>."
            f"{candidate_text}"
            "Use the current screen and resolved candidate. Do not copy placeholder values."
        )

    def _compact_context_for_protocol_recovery(self) -> None:
        """Keep only the system prompt and the most recent valid completed turn."""
        if not self._context:
            return
        system = self._context[0] if self._context[0].get("role") == "system" else None
        body = self._context[1:] if system is not None else self._context
        last_pair: list[dict[str, Any]] = []
        for index in range(len(body) - 2, -1, -1):
            if (
                body[index].get("role") == "user"
                and index + 1 < len(body)
                and body[index + 1].get("role") == "assistant"
            ):
                last_pair = [body[index], body[index + 1]]
                break
        self._context = ([system] if system is not None else []) + last_pair

    def _primary_app_candidate(self) -> dict[str, Any] | None:
        likely = self._device_app_context.get("likely_goal_apps", [])
        if not isinstance(likely, list) or not likely:
            return None
        resolution = likely[0].get("resolution", {}) if isinstance(likely[0], dict) else {}
        matched = resolution.get("matched_app") if isinstance(resolution, dict) else None
        if isinstance(matched, dict):
            return matched
        candidates = likely[0].get("candidates", []) if isinstance(likely[0], dict) else []
        if candidates and isinstance(candidates[0], dict):
            app = candidates[0].get("app")
            return app if isinstance(app, dict) else None
        return None

    def _build_previous_execution_info(self) -> str:
        previous = self.state.last_execution
        if not previous:
            return ""
        payload = {
            "success": previous.get("success"),
            "command_success": previous.get("command_success"),
            "should_finish": previous.get("should_finish"),
            "message": previous.get("message"),
            "error_code": previous.get("error_code"),
            "action": previous.get("action"),
            "verification": previous.get("verification"),
            "recovery": previous.get("recovery"),
            "stagnant_observation_count": self.state.stagnant_observation_count,
        }
        return "** Previous Action Result **\n" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        )

    def _trim_context(self) -> None:
        if len(self._context) <= 2:
            return
        system = self._context[0]
        body = self._context[1:]
        current_user = body[-1] if body and body[-1].get("role") == "user" else None
        completed = body[:-1] if current_user is not None else body
        pairs: list[list[dict[str, Any]]] = []
        index = 0
        while index + 1 < len(completed):
            first, second = completed[index], completed[index + 1]
            if first.get("role") == "user" and second.get("role") == "assistant":
                pairs.append([first, second])
                index += 2
            else:
                index += 1
        new_context = [system]
        for pair in pairs[-self.agent_config.context_turns :]:
            new_context.extend(pair)
        if current_user is not None:
            new_context.append(current_user)
        self._context = new_context

    def _record_observation(self, observation: ScreenObservation, *, source: str) -> None:
        payload = {
            **observation.to_screen_info(),
            "current_app": observation.current_app,
            "step": self._step_count,
            "source": source,
        }
        self.state.update_observation(payload, step=self._step_count)
        self._record_event(
            EventType.OBSERVATION,
            "Screen observed",
            dict(self.state.last_observation),
        )

    def _record_command_execution(
        self,
        action: dict[str, Any],
        execution: ActionResult,
        *,
        recovery: bool = False,
    ) -> None:
        self._record_event(
            EventType.EXECUTION,
            execution.message or "Action command completed",
            {
                "command_success": execution.success,
                "should_finish": execution.should_finish,
                "action": action,
                "message": execution.message,
                "requires_confirmation": execution.requires_confirmation,
                "error_code": execution.error_code,
                "metadata": execution.metadata,
                "step": self._step_count,
                "recovery": recovery,
            },
        )

    def _record_verification(
        self,
        action: dict[str, Any],
        verification: VerificationResult,
    ) -> None:
        self._record_event(
            EventType.VERIFICATION,
            verification.message,
            {
                **verification.to_dict(),
                "action": action,
                "step": self._step_count,
            },
        )

    def _record_recovery_outcome(self, outcome: RecoveryOutcome) -> None:
        self._record_event(
            EventType.RECOVERY,
            outcome.message,
            {**outcome.to_dict(), "step": self._step_count, "stage": "outcome"},
        )

    def _observation_from_state(self) -> ScreenObservation:
        """Best-effort fallback used only for a bounded safe recovery retry."""
        observation = self._observe_with_retries()
        self._record_observation(observation, source="recovery_retry_before")
        return observation

    def _runtime_limit_reached(self) -> bool:
        return bool(
            self.agent_config.max_runtime_seconds > 0
            and self.state.started_at is not None
            and time.time() - self.state.started_at
            >= self.agent_config.max_runtime_seconds
        )

    def _failure_limit_reached(self) -> bool:
        limit = self.agent_config.max_consecutive_failures
        return limit > 0 and self.state.consecutive_failures >= limit

    def _should_block_repeated_action(self, action: dict[str, Any]) -> bool:
        limit = self.agent_config.max_repeated_actions
        if limit <= 0 or action.get("_metadata") != "do":
            return False
        if action.get("action") in {"Wait", "Note", "Interact", "Take_over"}:
            return False
        return (
            self.state.repeated_action_count >= limit
            and self.state.stagnant_observation_count > 0
        )

    @staticmethod
    def _action_signature(action: dict[str, Any]) -> str:
        return json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _start_run(self, task: str) -> None:
        self._context.clear()
        self._step_count = 0
        self._pending_observation = None
        self._device_app_context = {}
        self._pure_launch_intent = None
        self._pure_launch_resolution = None
        self._direct_route_attempted = False
        self._strict_action_recovery = None
        self.state.start(task)
        self.recovery_manager.reset()
        self.action_handler.set_task(task)
        self.trajectory = TrajectoryRecorder(
            output_dir=self.agent_config.trajectory_dir,
            task=task,
        )
        self.last_trajectory_path = None
        self._transition(AgentPhase.INITIALIZING, "Initialize task runtime")
        self._record_event(EventType.START, "Task started", {"task": task})
        self._initialize_app_awareness(task)

    def _initialize_app_awareness(self, task: str) -> None:
        """Refresh the device app catalog without making task startup brittle."""
        if self.app_catalog is None:
            return
        try:
            if self.agent_config.app_catalog.refresh_on_start:
                apps = self.app_catalog.refresh()
            else:
                apps = self.app_catalog.ensure_loaded()
            self._device_app_context = self.app_catalog.build_prompt_context(task)
            self._pure_launch_intent = extract_pure_launch_intent(task)
            if self._pure_launch_intent is not None and hasattr(self.app_catalog, "resolve"):
                try:
                    self._pure_launch_resolution = self.app_catalog.resolve(
                        self._pure_launch_intent.query,
                        refresh_if_missing=False,
                    )
                except Exception as exc:
                    logger.warning("Pure-launch resolution failed: %s", exc)
            self._record_event(
                EventType.APP_CATALOG,
                "Device application catalog prepared",
                {
                    "available": bool(apps),
                    "app_count": len(apps),
                    "catalog_error": self.app_catalog.last_error,
                    "likely_goal_apps": self._device_app_context.get(
                        "likely_goal_apps", []
                    ),
                    "pure_launch_intent": (
                        self._pure_launch_intent.query
                        if self._pure_launch_intent is not None
                        else None
                    ),
                    "deterministic_resolution": (
                        self._pure_launch_resolution.to_dict()
                        if self._pure_launch_resolution is not None
                        else None
                    ),
                    "step": self._step_count,
                },
            )
        except Exception as exc:
            logger.warning("App awareness initialization failed: %s", exc)
            self._device_app_context = {
                "catalog_available": False,
                "catalog_error": str(exc),
                "launch_policy": (
                    "The device app catalog is unavailable. Use only a known exact app "
                    "name or package; do not guess among similar applications."
                ),
            }
            self._record_event(
                EventType.APP_CATALOG,
                "Device application catalog unavailable",
                {
                    "available": False,
                    "catalog_error": str(exc),
                    "step": self._step_count,
                },
            )

    def _finalize_run(self, result: StepResult) -> None:
        if self.state.finished:
            return
        target = (
            AgentPhase.CANCELLED
            if result.error_code == "interrupted"
            else AgentPhase.COMPLETED
            if result.success
            else AgentPhase.FAILED
        )
        if not self.state.phase.terminal:
            self._transition(target, result.message or "Task finalized")
        self.state.finish(success=result.success, message=result.message)
        result.phase = self.state.phase.value
        self.trajectory.mark_finished(success=result.success, message=result.message)
        self._record_event(
            EventType.FINISH,
            result.message or ("Task completed" if result.success else "Task failed"),
            {
                "success": result.success,
                "steps": self._step_count,
                "error_code": result.error_code,
                "phase": self.state.phase.value,
                "recoveries": self.state.recovery_count,
            },
        )
        if not self.agent_config.save_trajectory:
            return
        try:
            self.last_trajectory_path = str(
                self.trajectory.save(state=self.state.to_dict())
            )
        except Exception as exc:
            logger.exception("Failed to save trajectory: %s", exc)
            self.last_trajectory_path = None

    def _transition(
        self,
        target: AgentPhase,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        transition = self.state.machine.transition(
            target,
            reason=reason,
            step=self._step_count,
            metadata=metadata,
        )
        if transition is not None:
            self._record_event(
                EventType.PHASE_CHANGE,
                reason,
                {**transition.to_dict(), "step": self._step_count},
            )

    def _record_event(
        self,
        event_type: EventType,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_payload = payload or {}
        self.trajectory.add(
            event_type.value,
            normalized_payload,
            step=normalized_payload.get("step"),
            message=message,
        )
        self._emit(event_type, message, normalized_payload)

    def _emit(
        self,
        event_type: EventType,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(
                AgentEvent(type=event_type, message=message, payload=payload or {})
            )
        except Exception:
            logger.exception("Event callback failed for %s", event_type.value)

    @property
    def context(self) -> list[dict[str, Any]]:
        return list(self._context)

    @property
    def step_count(self) -> int:
        return self._step_count
