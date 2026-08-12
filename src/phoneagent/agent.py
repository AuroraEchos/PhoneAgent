"""Android-only PhoneAgent runtime."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from phoneagent.actions import (
    ActionHandler,
    ActionParseError,
    ActionResult,
    do,
    finish,
    parse_action,
)
from phoneagent.config import TaskEntryApp, get_messages, get_system_prompt, infer_task_entry_app
from phoneagent.config.apps import get_package_name
from phoneagent.devices import AndroidDevice, ScreenObservation
from phoneagent.model import (
    AsyncOpenAIModelClient,
    BaseModelClient,
    MessageBuilder,
    ModelClient,
    ModelConfig,
    ModelProtocolError,
    ModelRequestCancelled,
    ModelResponse,
    append_observation_message,
    build_protocol_retry_context,
    prepare_protocol_recovery,
    trim_context,
)
from phoneagent.runtime import (
    ActionVerifier,
    AgentEvent,
    AgentPhase,
    AgentState,
    EventType,
    FreshnessConfig,
    ObservationFreshnessGuard,
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


def _normalize_action_signature(action: dict[str, Any]) -> dict[str, Any]:
    """Round all numeric values so int/float differences don't break signatures.

    ``250`` (int) and ``250.0`` (float) serialise differently in JSON.  This
    helper normalises every numeric leaf to a float rounded to 6 decimal places
    so the two forms produce identical signature strings.
    """
    result: dict[str, Any] = {}
    for key, value in action.items():
        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, int):
            result[key] = float(value)
        elif isinstance(value, float):
            result[key] = round(value, 6)
        elif isinstance(value, list):
            result[key] = [
                round(float(item), 6)
                if isinstance(item, (int, float)) and not isinstance(item, bool)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


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
    app_launch_timeout_seconds: float = 15.0
    protocol_retries: int = 1
    protocol_retry_max_tokens: int = 512
    freshness: FreshnessConfig = field(default_factory=FreshnessConfig)
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
        if self.app_launch_timeout_seconds <= 0:
            raise ValueError("app_launch_timeout_seconds must be positive")
        if self.protocol_retries < 0:
            raise ValueError("protocol_retries cannot be negative")
        if self.protocol_retry_max_tokens <= 0:
            raise ValueError("protocol_retry_max_tokens must be positive")


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


@dataclass(slots=True)
class _SelectedResponse:
    """One response selected by deterministic launch or model planning."""

    response: ModelResponse
    source: str


@dataclass(slots=True)
class _AcceptedAction:
    """A parsed action together with the response and source that produced it."""

    response: ModelResponse
    action: dict[str, Any]
    source: str


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
        model_client: BaseModelClient | None = None,
        api_callback: Callable[[str], str | None] | None = None,
        note_callback: Callable[[str], None] | None = None,
        async_model_client: AsyncOpenAIModelClient | None = None,
    ):
        self.agent_config = agent_config or AgentConfig()
        self.model_config = model_config or ModelConfig()
        self.device = device or AndroidDevice(
            device_id=self.agent_config.device_id,
            allow_fallback_screenshot=self.agent_config.allow_fallback_screenshot,
            app_launch_timeout_seconds=self.agent_config.app_launch_timeout_seconds,
        )
        self.model_client = model_client or ModelClient(self.model_config)
        self._async_model_client = async_model_client
        self._cancel_event = Event()
        self._cancel_message = "Task cancelled by user"
        self.action_handler = ActionHandler(
            device=self.device,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            api_callback=api_callback,
            note_callback=note_callback,
            cancel_event=self._cancel_event,
        )
        self.verifier = ActionVerifier(self.agent_config.verification)
        self.freshness_guard = ObservationFreshnessGuard(self.agent_config.freshness)
        self.recovery_manager = RecoveryManager(self.agent_config.recovery)
        self.event_callback = event_callback
        self.state = AgentState()
        self.trajectory = TrajectoryRecorder(output_dir=self.agent_config.trajectory_dir)
        self.last_trajectory_path: str | None = None
        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._pending_observation: ScreenObservation | None = None
        self._strict_action_recovery: str | None = None

    def run(self, task: str) -> str:
        """Run until completion, terminal failure, or configured limits.

        This is a synchronous wrapper around :meth:`_run_async`.  Callers that
        already run inside an event loop can call :meth:`run_async` directly.
        """
        return asyncio.run(self.run_async(task))

    async def run_async(self, task: str) -> str:
        """Async entry point – same contract as :meth:`run`."""
        if not str(task or "").strip():
            raise ValueError("task cannot be empty")
        self._start_run(str(task).strip())
        result: StepResult | None = None

        try:
            while self._step_count < self.agent_config.max_steps:
                if self._cancel_event.is_set():
                    result = self._cancelled_result()
                    break
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
                is_first = not any(message.get("role") == "system" for message in self._context)
                result = await self._execute_step_async(
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
        except asyncio.CancelledError:
            result = self._cancelled_result()

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

    def request_cancel(self, message: str = "Task cancelled by user") -> bool:
        """Request cooperative cancellation at the next safe runtime checkpoint."""
        if self.state.started_at is None or self.state.finished:
            return False
        self._cancel_message = str(message or "Task cancelled by user")
        self._cancel_event.set()
        return True

    def step(self, task: str | None = None) -> StepResult:
        """Execute exactly one observe-plan-execute-verify step (sync wrapper)."""
        return asyncio.run(self.step_async(task))

    async def step_async(self, task: str | None = None) -> StepResult:
        """Async step – same contract as :meth:`step`."""
        if self.state.finished:
            if not task:
                raise ValueError("task is required after a finished run")
            self._start_run(task)
        elif self.state.started_at is None:
            if not task:
                raise ValueError("task is required for the first step")
            self._start_run(task)

        is_first = not any(message.get("role") == "system" for message in self._context)
        result = await self._execute_step_async(
            (task or self.state.goal) if is_first else None,
            is_first=is_first,
        )
        if result.finished:
            self._finalize_run(result)
        return result

    def reset(self) -> None:
        """Clear model context, counters, current state and trajectory data."""
        self._context.clear()
        self._step_count = 0
        self._pending_observation = None
        self._strict_action_recovery = None
        self._cancel_event.clear()
        self._cancel_message = "Task cancelled by user"
        self.state.reset()
        self.recovery_manager.reset()
        self.trajectory = TrajectoryRecorder(output_dir=self.agent_config.trajectory_dir)
        self.last_trajectory_path = None

    def _initial_launch_target(
        self,
        observation: ScreenObservation,
        *,
        is_first: bool,
    ) -> TaskEntryApp | None:
        """Select a deterministic first launch only for an explicit task entry app."""
        if not is_first:
            return None
        target = infer_task_entry_app(self.state.goal)
        if target is None:
            return None
        current_package = str(observation.current_package or "").strip()
        current_name_package = get_package_name(observation.current_app)
        if target.package_name in {current_package, current_name_package}:
            return None
        return target

    async def _execute_step_async(
        self,
        user_prompt: str | None = None,
        is_first: bool = False,
    ) -> StepResult:
        self._step_count += 1
        self.state.begin_step(self._step_count)
        msgs = get_messages()
        observation = await self._acquire_step_observation_async()
        if isinstance(observation, StepResult):
            return observation

        initial_launch = self._prepare_step_context(
            observation,
            user_prompt=user_prompt,
            is_first=is_first,
        )
        selected = await self._select_step_response_async(
            observation,
            initial_launch=initial_launch,
            messages=msgs,
        )
        if isinstance(selected, StepResult):
            return selected

        accepted = await self._accept_step_action_async(selected, messages=msgs)
        if isinstance(accepted, StepResult):
            return accepted
        return await self._execute_accepted_action_async(accepted, observation)

    async def _acquire_step_observation_async(self) -> ScreenObservation | StepResult:
        """Acquire and validate the trusted observation that begins every step."""
        self._transition(AgentPhase.OBSERVING, "Acquire current device state")
        try:
            observation = await self._next_observation_async()
        except Exception as exc:
            if self._cancel_event.is_set():
                return self._cancelled_result()
            return await self._handle_runtime_failure_async(
                message=f"Observation failed: {exc}",
                error_code="observation_failed",
                thinking="",
                raw_model_output=None,
                action=None,
            )

        if self._cancel_event.is_set():
            return self._cancelled_result()
        if not observation.screenshot.available:
            return await self._handle_runtime_failure_async(
                message=observation.screenshot.error or "Screenshot unavailable",
                error_code="screenshot_unavailable",
                thinking="",
                raw_model_output=None,
                action=None,
            )
        if observation.screenshot.is_blank:
            return await self._handle_runtime_failure_async(
                message=(
                    "The captured screen is blank or protected. PhoneAgent will not "
                    "guess coordinates on an unobservable screen."
                ),
                error_code="protected_or_blank_screen",
                thinking="",
                raw_model_output=None,
                action=None,
            )
        return observation

    def _prepare_step_context(
        self,
        observation: ScreenObservation,
        *,
        user_prompt: str | None,
        is_first: bool,
    ) -> TaskEntryApp | None:
        """Append the observation and choose the deterministic planning source."""
        append_observation_message(
            self._context,
            observation=observation,
            state=self.state,
            system_prompt=self.agent_config.system_prompt or "",
            user_prompt=user_prompt,
            is_first=is_first,
            strict_recovery=self._strict_action_recovery,
            notes=self.action_handler.notes,
            api_callback_available=self.action_handler.api_callback is not None,
        )
        self._strict_action_recovery = None
        trim_context(self._context, self.agent_config.context_turns)
        initial_launch = self._initial_launch_target(observation, is_first=is_first)
        self._transition(
            AgentPhase.PLANNING,
            (
                "Resolve explicit entry application"
                if initial_launch is not None
                else "Request one constrained model action"
            ),
        )
        return initial_launch

    async def _select_step_response_async(
        self,
        observation: ScreenObservation,
        *,
        initial_launch: TaskEntryApp | None,
        messages: dict[str, str],
    ) -> _SelectedResponse | StepResult:
        """Select a deterministic launch response or request a model response."""
        if initial_launch is not None:
            action_text = (
                'do(action="Launch", app='
                + json.dumps(initial_launch.app_name, ensure_ascii=False)
                + ")"
            )
            response = ModelResponse(
                thinking=(
                    f"Runtime identified {initial_launch.app_name} as the explicit entry "
                    "application and selected deterministic launch before visual planning."
                ),
                action=action_text,
                raw_content=action_text,
                attempts=0,
            )
            self._record_event(
                EventType.THINKING,
                f"Prioritize deterministic launch of {initial_launch.app_name}",
                {
                    "step": self._step_count,
                    "source": "runtime_initial_launch",
                    "app": initial_launch.app_name,
                    "package_name": initial_launch.package_name,
                    "evidence": initial_launch.evidence,
                },
            )
            return _SelectedResponse(response=response, source="runtime_initial_launch")
        return await self._request_step_model_response_async(observation, messages=messages)

    async def _request_step_model_response_async(
        self,
        observation: ScreenObservation,
        *,
        messages: dict[str, str],
    ) -> _SelectedResponse | StepResult:
        """Request one model action and normalize request failures into step results."""
        if self.agent_config.verbose:
            print("\n" + "=" * 50)
            print(f"{messages['thinking']}:")
            print("-" * 50)

        request_context = self._context
        protocol_retry_token_limit = min(
            self.model_config.max_tokens,
            self.agent_config.protocol_retry_max_tokens,
        )
        for protocol_attempt in range(1, self.agent_config.protocol_retries + 2):
            is_protocol_retry = protocol_attempt > 1
            self._record_event(
                EventType.MODEL_REQUEST,
                "Retrying model action protocol" if is_protocol_retry else "Requesting model",
                {
                    "step": self._step_count,
                    "message_count": len(request_context),
                    "current_app": observation.current_app,
                    "phase": self.state.phase.value,
                    "protocol_attempt": protocol_attempt,
                    "protocol_retry": is_protocol_retry,
                },
            )
            response: ModelResponse | None = None
            try:
                response = await self._request_model_async(
                    context=request_context,
                    max_tokens=(
                        protocol_retry_token_limit
                        if is_protocol_retry
                        else None
                    ),
                )
                # Validate the inner action schema here so malformed arguments
                # receive the same cheap same-turn retry as a missing call.
                parse_action(response.action)
            except (ModelProtocolError, ActionParseError) as exc:
                if self._cancel_event.is_set():
                    return self._cancelled_result()
                truncated = isinstance(exc, ModelProtocolError) and exc.truncated
                protocol_error_code = (
                    exc.error_code
                    if isinstance(exc, ModelProtocolError)
                    else "invalid_action_arguments"
                )
                metrics = (
                    exc.metrics
                    if isinstance(exc, ModelProtocolError)
                    else self._model_response_metrics(response)
                )
                raw_content = (
                    exc.raw_content
                    if isinstance(exc, ModelProtocolError)
                    else (response.raw_content if response is not None else None)
                )
                finish_reason = (
                    exc.finish_reason
                    if isinstance(exc, ModelProtocolError)
                    else (response.finish_reason if response is not None else None)
                )
                message = (
                    "Model output was truncated before a valid action was completed "
                    f"(finish_reason={finish_reason}): {exc}"
                    if truncated
                    else f"Model protocol error [{protocol_error_code}]: {exc}"
                )
                logger.warning("%s", message)
                self._record_event(
                    EventType.MODEL_RESPONSE,
                    "Truncated model response rejected" if truncated else "Model response rejected by protocol",
                    {
                        "raw_content": raw_content,
                        "protocol_error": str(exc),
                        "protocol_error_code": protocol_error_code,
                        "protocol_attempt": protocol_attempt,
                        "finish_reason": finish_reason,
                        "truncated": truncated,
                        "metrics": metrics,
                        "step": self._step_count,
                    },
                )
                self._record_event(
                    EventType.METRICS,
                    "Rejected model response timing captured",
                    {
                        "metrics": metrics,
                        "protocol_attempt": protocol_attempt,
                        "protocol_rejected": True,
                        "step": self._step_count,
                    },
                )
                if protocol_attempt <= self.agent_config.protocol_retries:
                    self._record_event(
                        EventType.PROTOCOL_RETRY,
                        "Retry one action-only response without advancing the agent step",
                        {
                            "protocol_error_code": protocol_error_code,
                            "protocol_attempt": protocol_attempt,
                            "next_protocol_attempt": protocol_attempt + 1,
                            "max_tokens": protocol_retry_token_limit,
                            "command_dispatched": False,
                            "metrics": metrics,
                            "step": self._step_count,
                        },
                    )
                    request_context = build_protocol_retry_context(
                        self._context,
                        reason=message,
                    )
                    continue

                runtime_error_code = "model_output_truncated" if truncated else protocol_error_code
                self._strict_action_recovery = prepare_protocol_recovery(
                    self._context,
                    reason=message,
                    rejected_action=(response.action if response is not None else raw_content),
                )
                return await self._handle_runtime_failure_async(
                    message=message,
                    error_code=runtime_error_code,
                    thinking="",
                    raw_model_output=raw_content,
                    action=None,
                    metadata={
                        "protocol_error_code": protocol_error_code,
                        "protocol_attempts": protocol_attempt,
                        "command_dispatched": False,
                    },
                )
            except Exception as exc:
                if self._cancel_event.is_set():
                    return self._cancelled_result()
                logger.exception("Model request failed: %s", exc)
                if self._context and self._context[-1].get("role") == "user":
                    # No assistant turn exists, so the retry must attach a fresh screenshot.
                    self._context.pop()
                return await self._handle_runtime_failure_async(
                    message=f"Model request failed: {exc}",
                    error_code="model_request_failed",
                    thinking="",
                    raw_model_output=None,
                    action=None,
                )

            assert response is not None
            self._record_successful_model_response(
                response,
                protocol_attempt=protocol_attempt,
            )
            return _SelectedResponse(
                response=response,
                source="model_protocol_retry" if is_protocol_retry else "model",
            )

        raise AssertionError("protocol retry loop terminated unexpectedly")

    @staticmethod
    def _model_response_metrics(response: ModelResponse | None) -> dict[str, Any]:
        if response is None:
            return {}
        return {
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

    def _record_successful_model_response(
        self,
        response: ModelResponse,
        *,
        protocol_attempt: int = 1,
    ) -> None:
        metrics = self._model_response_metrics(response)
        self._record_event(
            EventType.MODEL_RESPONSE,
            "Model response received",
            {
                "thinking": response.thinking,
                "action": response.action,
                "raw_content": response.raw_content,
                "metrics": metrics,
                "protocol_attempt": protocol_attempt,
                "protocol_retries_used": protocol_attempt - 1,
                "step": self._step_count,
            },
        )
        self._record_event(
            EventType.METRICS,
            "Model timing captured",
            {
                "metrics": metrics,
                "protocol_attempt": protocol_attempt,
                "protocol_rejected": False,
                "step": self._step_count,
            },
        )

    async def _accept_step_action_async(
        self,
        selected: _SelectedResponse,
        *,
        messages: dict[str, str],
    ) -> _AcceptedAction | StepResult:
        """Parse, record, and append one response action to model history."""
        if self._cancel_event.is_set():
            return self._cancelled_result()
        response = selected.response
        try:
            action = parse_action(response.action)
        except ActionParseError as exc:
            error_code = "model_output_truncated" if response.truncated else "action_parse_error"
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
            self._strict_action_recovery = prepare_protocol_recovery(
                self._context,
                reason=message,
                rejected_action=response.action,
            )
            return await self._handle_runtime_failure_async(
                message=message,
                error_code=error_code,
                thinking=response.thinking,
                raw_model_output=response.raw_content,
                action=None,
            )

        self.state.update_action(
            action,
            step=self._step_count,
            signature=self._action_signature(action),
            coordinate_signature=self._action_coordinate_signature(action),
        )
        self._record_event(
            EventType.ACTION,
            (
                "Runtime selected deterministic initial app launch"
                if selected.source == "runtime_initial_launch"
                else "Parsed action"
            ),
            {
                "action": action,
                "thinking": response.thinking,
                "step": self._step_count,
                "repeated_action_count": self.state.repeated_action_count,
                "source": selected.source,
            },
        )
        if self.agent_config.verbose:
            print("-" * 50)
            print(f"{messages['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])
        self._context.append(
            MessageBuilder.create_assistant_message(response.to_assistant_message_content())
        )
        self._transition(AgentPhase.EXECUTING, "Execute validated Android action")
        return _AcceptedAction(response=response, action=action, source=selected.source)

    async def _execute_accepted_action_async(
        self,
        accepted: _AcceptedAction,
        observation: ScreenObservation,
    ) -> StepResult:
        """Execute one accepted action, then verify and recover when required."""
        action = accepted.action
        if self._cancel_event.is_set():
            return self._cancelled_result()

        execution_observation = observation
        confirmation_checked = False
        if self.freshness_guard.requires_check(action):
            confirmation = await asyncio.to_thread(
                self.action_handler.request_confirmation,
                action,
            )
            confirmation_checked = True
            if confirmation is not None:
                self._record_command_execution(action, confirmation)
                return self._terminal_action_step_result(accepted, confirmation)

            guarded = await self._guard_action_freshness_async(
                accepted,
                planned=observation,
            )
            if isinstance(guarded, StepResult):
                return guarded
            execution_observation = guarded

        execution = await self._execute_device_action_async(
            action,
            execution_observation,
            confirmation_checked=confirmation_checked,
        )
        self._record_command_execution(action, execution)

        if self._cancel_event.is_set():
            return self._cancelled_result(action=action, command_success=execution.success)
        if action.get("_metadata") == "finish" or execution.should_finish:
            return self._terminal_action_step_result(accepted, execution)
        return await self._evaluate_action_result_async(
            accepted,
            execution,
            execution_observation,
        )

    async def _guard_action_freshness_async(
        self,
        accepted: _AcceptedAction,
        *,
        planned: ScreenObservation,
    ) -> ScreenObservation | StepResult:
        """Revalidate a screenshot-bound action immediately before dispatch."""
        started = time.monotonic()
        try:
            current = await self._observe_with_retries_async(
                retries=self.agent_config.freshness.observation_retries,
                retry_delay=self.agent_config.freshness.observation_retry_delay,
            )
        except Exception as exc:
            return await self._handle_runtime_failure_async(
                message=f"Pre-action observation failed: {exc}",
                error_code="pre_action_observation_failed",
                thinking=accepted.response.thinking,
                raw_model_output=accepted.response.raw_content,
                action=accepted.action,
                metadata={
                    "command_dispatched": False,
                    "exception_type": type(exc).__name__,
                },
            )
        if self._cancel_event.is_set():
            return self._cancelled_result(action=accepted.action)

        self._record_observation(current, source="pre_action_freshness")
        result = self.freshness_guard.check(
            action=accepted.action,
            planned=planned,
            current=current,
        )
        result.check_duration_seconds = time.monotonic() - started
        payload = {
            **result.to_dict(),
            "action": accepted.action,
            "step": self._step_count,
            "dispatch_authorized": result.fresh,
            "command_dispatched": False,
            "planned_screenshot_sha256": planned.screenshot.sha256,
            "current_screenshot_sha256": current.screenshot.sha256,
        }
        self._record_event(
            EventType.PRECONDITION,
            (
                "Pre-action visual state is compatible"
                if result.fresh
                else "Pre-action visual state changed; action invalidated"
            ),
            payload,
        )
        if result.fresh:
            return current

        self._pending_observation = current
        return await self._handle_runtime_failure_async(
            message=(
                "The live screen changed after the model observation. "
                "The coordinate action was not dispatched; replan from the fresh screen."
            ),
            error_code="pre_action_observation_changed",
            thinking=accepted.response.thinking,
            raw_model_output=accepted.response.raw_content,
            action=accepted.action,
            metadata=payload,
        )

    async def _execute_device_action_async(
        self,
        action: dict[str, Any],
        observation: ScreenObservation,
        *,
        confirmation_checked: bool = False,
    ) -> ActionResult:
        if self._should_block_repeated_action(action):
            return ActionResult(
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
        return await asyncio.to_thread(
            self.action_handler.execute,
            action,
            int(observation.screenshot.display_width or observation.screenshot.width),
            int(observation.screenshot.display_height or observation.screenshot.height),
            confirmation_checked=confirmation_checked,
        )

    def _terminal_action_step_result(
        self,
        accepted: _AcceptedAction,
        execution: ActionResult,
    ) -> StepResult:
        action = accepted.action
        self.state.update_execution(
            success=execution.success,
            command_success=None,
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
            thinking=accepted.response.thinking,
            message=message,
            raw_model_output=accepted.response.raw_content,
            error_code=execution.error_code,
            command_success=None,
            phase=self.state.phase.value,
        )

    async def _evaluate_action_result_async(
        self,
        accepted: _AcceptedAction,
        execution: ActionResult,
        observation: ScreenObservation,
    ) -> StepResult:
        action = accepted.action
        response = accepted.response
        verification = await self._verify_action_async(action, execution, observation)
        if self._cancel_event.is_set():
            return self._cancelled_result(action=action, command_success=execution.success)

        recovery_execution: _RecoveryExecution | None = None
        overall_success = verification.passed
        final_verification = verification
        error_code = verification.error_code or execution.error_code
        message = verification.message if not verification.passed else execution.message

        if not verification.passed:
            recovery_execution = await self._perform_recovery_async(
                action=action,
                execution=execution,
                verification=verification,
            )
            if self._cancel_event.is_set():
                return self._cancelled_result(action=action, command_success=execution.success)
            if recovery_execution.verification is not None:
                final_verification = recovery_execution.verification
            if recovery_execution.action_recovered:
                overall_success = True
                error_code = None
                message = recovery_execution.outcome.message
            elif recovery_execution.outcome.decision.terminal:
                message = recovery_execution.outcome.message
                error_code = recovery_execution.outcome.error_code or error_code

        recovery_succeeded = bool(recovery_execution and recovery_execution.outcome.success)
        if overall_success or recovery_succeeded:
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
        )
        if not overall_success and recovery_succeeded:
            # Successful mitigation gives the replanning turn a fresh failure budget.
            self.state.consecutive_failures = 0
        self.state.update_verification(final_verification.to_dict())
        if recovery_payload is not None:
            self.state.update_recovery(recovery_payload)

        finished = (
            bool(recovery_execution and recovery_execution.outcome.decision.terminal)
            or self._failure_limit_reached()
        )
        if not finished:
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

    async def _verify_action_async(
        self,
        action: dict[str, Any],
        execution: ActionResult,
        before: ScreenObservation,
    ) -> VerificationResult:
        result = await self._verify_action_once_async(
            action,
            execution,
            before,
            observation_source="post_action_verification",
        )
        action_name = str(action.get("action", ""))
        open_panel_actions = {"OpenNotifications", "OpenQuickSettings"}
        fallback_errors = {
            "system_panel_command_failed",
            "verification_system_panel_not_open",
        }
        if (
            action_name not in open_panel_actions
            or result.passed
            or self._cancel_event.is_set()
            or (result.error_code or execution.error_code) not in fallback_errors
        ):
            return result

        primary_attempt = {
            "stage": "primary",
            "success": execution.success,
            "error_code": execution.error_code,
            "verification": result.to_dict(),
            "metadata": dict(execution.metadata),
        }
        fallback_before = self._pending_observation or before
        width = int(fallback_before.screenshot.display_width or fallback_before.screenshot.width)
        height = int(fallback_before.screenshot.display_height or fallback_before.screenshot.height)
        self._transition(
            AgentPhase.EXECUTING,
            f"Use hidden edge-gesture fallback for {action_name}",
        )
        fallback_execution = await asyncio.to_thread(
            self.action_handler.execute_system_panel_fallback,
            action,
            width,
            height,
        )
        self._record_command_execution(action, fallback_execution)

        final_result = await self._verify_action_once_async(
            action,
            fallback_execution,
            fallback_before,
            observation_source="system_panel_fallback_verification",
        )
        attempts = [
            primary_attempt,
            {
                "stage": "fallback",
                "success": fallback_execution.success,
                "error_code": fallback_execution.error_code,
                "verification": final_result.to_dict(),
                "metadata": dict(fallback_execution.metadata),
            },
        ]
        execution.metadata = {
            **dict(execution.metadata),
            "system_panel_attempts": attempts,
            "fallback_used": True,
            "final_transport": "gesture",
        }
        final_result.metadata["system_panel_attempts"] = attempts
        if fallback_execution.success:
            execution.success = True
            execution.error_code = None
            execution.message = (
                f"{action_name} completed using the edge-gesture fallback"
                if final_result.passed
                else fallback_execution.message
            )
        return final_result

    async def _verify_action_once_async(
        self,
        action: dict[str, Any],
        execution: ActionResult,
        before: ScreenObservation,
        *,
        observation_source: str,
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
                await asyncio.sleep(self.agent_config.verification.settle_delay_seconds)
            try:
                after = await self._observe_with_retries_async(
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
                self._record_observation(after, source=observation_source)
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

    async def _perform_recovery_async(
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
            return await self._recover_by_observation_async(decision)

        if decision.strategy == RecoveryStrategy.RETRY_ACTION:
            return await self._recover_by_action_retry_async(decision, action)

        if decision.strategy == RecoveryStrategy.TAKEOVER:
            try:
                self._transition(AgentPhase.WAITING_USER, "Manual takeover required")
                takeover = await asyncio.to_thread(
                    self.action_handler.execute,
                    do(action="Take_over", message=decision.reason),
                    1,
                    1,
                )
                if not takeover.success:
                    raise RuntimeError(takeover.message or "Manual takeover failed")
                observation = await self._observe_with_retries_async()
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
                self._record_recovery_outcome(outcome)
                return _RecoveryExecution(outcome=outcome)

        decision.terminal = True
        outcome = RecoveryOutcome(
            decision=decision,
            success=False,
            message="No executable recovery strategy was selected",
            error_code="recovery_strategy_unhandled",
        )
        self._record_recovery_outcome(outcome)
        return _RecoveryExecution(outcome=outcome)

    async def _recover_by_observation_async(self, decision) -> _RecoveryExecution:
        if self.agent_config.recovery.retry_delay_seconds > 0:
            await asyncio.sleep(self.agent_config.recovery.retry_delay_seconds)
        try:
            observation = await self._observe_with_retries_async()
            if observation.screenshot.is_blank:
                raise RuntimeError("Recovered observation is blank or protected")
            self._record_observation(observation, source="recovery_reobserve")
            self._pending_observation = observation
            outcome = RecoveryOutcome(
                decision=decision,
                success=True,
                message="Fresh observation acquired for replanning",
            )
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome, observation=observation)
        except Exception as exc:
            outcome = RecoveryOutcome(
                decision=decision,
                success=False,
                message=f"Reobservation recovery failed: {exc}",
                error_code="recovery_reobserve_failed",
            )
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

    async def _recover_by_action_retry_async(
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
            self._record_recovery_outcome(outcome)
            return _RecoveryExecution(outcome=outcome)

        if self.agent_config.recovery.retry_delay_seconds > 0:
            await asyncio.sleep(self.agent_config.recovery.retry_delay_seconds)
        before = self._pending_observation or await self._observation_from_state_async()
        self._transition(AgentPhase.EXECUTING, "Retry bounded safe action")
        width = int(before.screenshot.display_width or before.screenshot.width)
        height = int(before.screenshot.display_height or before.screenshot.height)
        retry_execution = await asyncio.to_thread(
            self.action_handler.execute,
            action,
            width,
            height,
        )
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

        retry_verification = await self._verify_action_async(action, retry_execution, before)
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

    async def _handle_runtime_failure_async(
        self,
        *,
        message: str,
        error_code: str,
        thinking: str,
        raw_model_output: str | None,
        action: dict[str, Any] | None,
        metadata: dict[str, Any] | None = None,
    ) -> StepResult:
        if self._cancel_event.is_set():
            return self._cancelled_result(action=action)
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
            command_success=None,
            observable_effect_verified=False,
            semantic_effect_verified=False,
            error_code=error_code,
            metadata=dict(metadata or {}),
        )
        self._record_event(
            EventType.ERROR,
            message,
            {
                "error_code": error_code,
                "step": self._step_count,
                "metadata": dict(metadata or {}),
            },
        )
        if self._cancel_event.is_set():
            return self._cancelled_result(action=action)
        recovery = await self._perform_recovery_async(
            action=action,
            execution=execution,
            verification=verification,
        )
        recovery_payload = recovery.outcome.to_dict()
        recovery_succeeded = recovery.outcome.success
        if recovery_succeeded:
            self.recovery_manager.mark_success()
        self.state.update_execution(
            success=False,
            command_success=None,
            should_finish=recovery.outcome.decision.terminal,
            message=message,
            action=action,
            error_code=error_code,
            metadata=dict(metadata or {}),
        )
        if recovery_succeeded:
            # A successful reobserve/replan resolves this failure episode. Keep
            # the total recovery budget, but do not treat a safe zero-touch
            # conflict as a growing streak of failed device commands.
            self.state.consecutive_failures = 0
        self.state.update_verification(verification.to_dict())
        self.state.update_recovery(recovery_payload)
        finished = recovery.outcome.decision.terminal or self._failure_limit_reached()
        return StepResult(
            success=False,
            finished=finished,
            action=action,
            thinking=thinking,
            message=message,
            raw_model_output=raw_model_output,
            error_code=error_code,
            command_success=None,
            verification=verification.to_dict(),
            recovery=recovery_payload,
            phase=self.state.phase.value,
        )

    async def _next_observation_async(self) -> ScreenObservation:
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
        observation = await self._observe_with_retries_async()
        self._record_observation(observation, source="step_observation")
        return observation

    async def _observe_with_retries_async(
        self,
        *,
        retries: int | None = None,
        retry_delay: float | None = None,
    ) -> ScreenObservation:
        retries = self.agent_config.observation_retries if retries is None else retries
        retry_delay = (
            self.agent_config.observation_retry_delay if retry_delay is None else retry_delay
        )
        attempts = retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.to_thread(self.device.observe)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                await asyncio.sleep(retry_delay * attempt)
        assert last_error is not None
        raise last_error

    async def _request_model_async(
        self,
        *,
        context: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        """Send a model request, preferring the async client when available."""
        request_context = self._context if context is None else context
        if self._async_model_client is not None:
            async_kwargs: dict[str, Any] = {
                "print_stream": self.agent_config.verbose,
                "cancel_event": self._cancel_event,
            }
            if max_tokens is not None and isinstance(
                self._async_model_client, BaseModelClient
            ):
                async_kwargs["max_tokens"] = max_tokens
            request_task = asyncio.create_task(
                self._async_model_client.request(
                    request_context,
                    **async_kwargs,
                )
            )
            cancel_task = asyncio.create_task(self._wait_for_cancel_request())
            done, _pending = await asyncio.wait(
                {request_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_task in done:
                request_task.cancel()
                with suppress(asyncio.CancelledError, ModelRequestCancelled):
                    await request_task
                raise ModelRequestCancelled("Model request cancelled")
            cancel_task.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_task
            return await request_task

        kwargs: dict[str, Any] = {"print_stream": self.agent_config.verbose}
        if isinstance(self.model_client, BaseModelClient):
            kwargs["cancel_event"] = self._cancel_event
            kwargs["max_tokens"] = max_tokens
        return await asyncio.to_thread(self.model_client.request, request_context, **kwargs)

    async def _wait_for_cancel_request(self) -> None:
        while not self._cancel_event.is_set():
            await asyncio.sleep(0.05)

    def _record_observation(self, observation: ScreenObservation, *, source: str) -> None:
        payload = {
            **observation.to_screen_info(),
            "current_app": observation.current_app,
            "content_sha256": self.verifier.visual_signature(observation),
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
        command_success = None if action.get("_metadata") == "finish" else execution.success
        self._record_event(
            EventType.EXECUTION,
            execution.message or "Action command completed",
            {
                "command_success": command_success,
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

    async def _observation_from_state_async(self) -> ScreenObservation:
        """Async variant of :meth:`_observation_from_state`."""
        observation = await self._observe_with_retries_async()
        self._record_observation(observation, source="recovery_retry_before")
        return observation

    def _runtime_limit_reached(self) -> bool:
        return bool(
            self.agent_config.max_runtime_seconds > 0
            and self.state.started_at is not None
            and time.time() - self.state.started_at >= self.agent_config.max_runtime_seconds
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
        if self.state.stagnant_observation_count <= 0:
            return False
        full_repeat = self.state.repeated_action_count >= limit
        coord_repeat = self.state.repeated_coordinate_count >= limit
        return full_repeat or coord_repeat

    @staticmethod
    def _action_signature(action: dict[str, Any]) -> str:
        """Create a deterministic signature that normalizes numeric coordinates.

        Int/float differences (``250`` vs ``250.0``) produce the same signature
        so the runtime does not treat them as distinct actions.
        """
        normalized = _normalize_action_signature(action)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _action_coordinate_signature(action: dict[str, Any]) -> str:
        """Compact signature that only compares action type and coordinates.

        Intentionally ignores ``description``, ``message``, ``sensitive`` and
        other metadata so the runtime can detect same-location taps regardless
        of how the model phrases the intent.
        """
        coordinates: dict[str, Any] = {}
        for field in ("element", "start", "end"):
            value = action.get(field)
            if value is not None:
                coordinates[field] = value
        if not coordinates:
            return ""
        parts: dict[str, Any] = {"action": action.get("action"), **coordinates}
        return json.dumps(_normalize_action_signature(parts), ensure_ascii=False, sort_keys=True)

    def _start_run(self, task: str) -> None:
        self._context.clear()
        self._step_count = 0
        self._pending_observation = None
        self._strict_action_recovery = None
        self._cancel_event.clear()
        self._cancel_message = "Task cancelled by user"
        transition = self.state.start(task)
        self.recovery_manager.reset()
        self.action_handler.set_task(task)
        self.trajectory = TrajectoryRecorder(
            output_dir=self.agent_config.trajectory_dir,
            task=task,
        )
        self.last_trajectory_path = None
        self._record_phase_transition(transition)
        self._record_event(EventType.START, "Task started", {"task": task})

    def _finalize_run(self, result: StepResult) -> None:
        if self.state.finished:
            return
        keyboard_restore_error = self.action_handler.restore_input_method()
        if keyboard_restore_error:
            logger.warning("Failed to restore input method: %s", keyboard_restore_error)
            self._record_event(
                EventType.ERROR,
                "Failed to restore the input method after task execution",
                {
                    "error_code": "keyboard_restore_failed",
                    "error": keyboard_restore_error,
                },
                step=self._step_count,
            )
        transition = (
            self.state.cancel(message=result.message)
            if result.error_code in {"cancelled", "interrupted"}
            else self.state.finish(success=result.success, message=result.message)
        )
        self._record_phase_transition(transition)
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
            self.last_trajectory_path = str(self.trajectory.save(state=self.state.to_dict()))
        except Exception as exc:
            logger.exception("Failed to save trajectory: %s", exc)
            self.last_trajectory_path = None

    def _cancelled_result(
        self,
        *,
        action: dict[str, Any] | None = None,
        command_success: bool | None = None,
    ) -> StepResult:
        return StepResult(
            success=False,
            finished=True,
            action=action,
            thinking="",
            message=self._cancel_message,
            error_code="cancelled",
            command_success=command_success,
            phase=self.state.phase.value,
        )

    def _transition(
        self,
        target: AgentPhase,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        transition = self.state.transition(
            target,
            reason=reason,
            metadata=metadata,
        )
        self._record_phase_transition(transition)

    def _record_phase_transition(self, transition: dict[str, Any] | None) -> None:
        if transition is not None:
            self._record_event(
                EventType.PHASE_CHANGE,
                str(transition.get("reason", "")),
                transition,
                step=self._step_count,
            )

    def _record_event(
        self,
        event_type: EventType,
        message: str = "",
        payload: dict[str, Any] | None = None,
        *,
        step: int | None = None,
    ) -> None:
        normalized_payload = deepcopy(payload or {})
        payload_step = normalized_payload.pop("step", None)
        event = AgentEvent(
            type=event_type,
            message=message,
            payload=normalized_payload,
            step=step if step is not None else payload_step,
        )
        self.trajectory.add_event(event)
        self._emit(event)

    def _emit(self, event: AgentEvent) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event)
        except Exception:
            logger.exception("Event callback failed for %s", event.type.value)

    @property
    def context(self) -> list[dict[str, Any]]:
        return list(self._context)

    @property
    def step_count(self) -> int:
        return self._step_count
