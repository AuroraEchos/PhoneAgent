"""Single-source runtime state for one PhoneAgent task."""

from __future__ import annotations

from copy import deepcopy
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentPhase(str, Enum):
    """Lifecycle phases of one PhoneAgent task."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    OBSERVING = "observing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class StateTransitionError(RuntimeError):
    """Raised when the runtime attempts an illegal phase transition."""


_ALLOWED_TRANSITIONS: dict[AgentPhase, set[AgentPhase]] = {
    AgentPhase.IDLE: {AgentPhase.INITIALIZING},
    AgentPhase.INITIALIZING: {AgentPhase.OBSERVING, AgentPhase.FAILED, AgentPhase.CANCELLED},
    AgentPhase.OBSERVING: {
        AgentPhase.PLANNING,
        AgentPhase.RECOVERING,
        AgentPhase.COMPLETED,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.PLANNING: {
        AgentPhase.EXECUTING,
        AgentPhase.RECOVERING,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.EXECUTING: {
        AgentPhase.VERIFYING,
        AgentPhase.RECOVERING,
        AgentPhase.WAITING_USER,
        AgentPhase.COMPLETED,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.VERIFYING: {
        AgentPhase.EXECUTING,
        AgentPhase.OBSERVING,
        AgentPhase.RECOVERING,
        AgentPhase.COMPLETED,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.RECOVERING: {
        AgentPhase.OBSERVING,
        AgentPhase.EXECUTING,
        AgentPhase.WAITING_USER,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.WAITING_USER: {
        AgentPhase.OBSERVING,
        AgentPhase.RECOVERING,
        AgentPhase.FAILED,
        AgentPhase.CANCELLED,
    },
    AgentPhase.COMPLETED: set(),
    AgentPhase.FAILED: set(),
    AgentPhase.CANCELLED: set(),
}


@dataclass(slots=True)
class AgentState:
    """Current task state.

    The trajectory event stream is the audit history. This object intentionally
    stores only the latest working state so phase and execution history cannot
    diverge across multiple representations.
    """

    goal: str = ""
    phase: AgentPhase = AgentPhase.IDLE
    current_step: int = 0
    current_app: str = ""
    target_app: str = ""
    last_observation: dict[str, Any] = field(default_factory=dict)
    last_action_signature: str = ""
    last_coordinate_signature: str = ""
    repeated_action_count: int = 0
    repeated_coordinate_count: int = 0
    stagnant_observation_count: int = 0
    last_execution: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    recovery_count: int = 0
    success: bool | None = None
    final_message: str = ""
    started_at: float | None = None
    finished_at: float | None = None

    def reset(self) -> None:
        self.goal = ""
        self.phase = AgentPhase.IDLE
        self.current_step = 0
        self.current_app = ""
        self.target_app = ""
        self.last_observation.clear()
        self.last_action_signature = ""
        self.last_coordinate_signature = ""
        self.repeated_action_count = 0
        self.repeated_coordinate_count = 0
        self.stagnant_observation_count = 0
        self.last_execution.clear()
        self.failures.clear()
        self.consecutive_failures = 0
        self.recovery_count = 0
        self.success = None
        self.final_message = ""
        self.started_at = None
        self.finished_at = None

    @property
    def finished(self) -> bool:
        """Whether the lifecycle phase is terminal."""
        return self.phase.terminal

    def start(self, goal: str) -> dict[str, Any]:
        """Reset the task and enter the initializing phase."""
        self.reset()
        self.goal = goal
        self.started_at = time.time()
        transition = self._apply_transition(
            AgentPhase.INITIALIZING,
            reason="Initialize task runtime",
        )
        assert transition is not None
        return transition

    def transition(
        self,
        target: AgentPhase,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Validate and apply one non-terminal phase transition.

        The returned payload is recorded directly as a trajectory event; no
        second in-memory transition history is retained.
        """
        if target.terminal:
            raise StateTransitionError("Use finish() or cancel() to enter a terminal phase")
        return self._apply_transition(target, reason=reason, metadata=metadata)

    def _apply_transition(
        self,
        target: AgentPhase,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if target == self.phase:
            return None
        if self.phase.terminal:
            raise StateTransitionError(
                f"Cannot transition terminal phase {self.phase.value} to {target.value}"
            )
        if target not in _ALLOWED_TRANSITIONS[self.phase]:
            raise StateTransitionError(
                f"Illegal PhoneAgent transition: {self.phase.value} -> {target.value}"
            )
        previous = self.phase
        self.phase = target
        return {
            "previous": previous.value,
            "current": target.value,
            "reason": reason,
            "metadata": deepcopy(metadata or {}),
        }

    def begin_step(self, step: int) -> None:
        if isinstance(step, bool) or not isinstance(step, int):
            raise TypeError("step must be an integer")
        if step < 0:
            raise ValueError("step cannot be negative")
        if step < self.current_step:
            raise ValueError(f"step cannot move backwards: {self.current_step} -> {step}")
        self.current_step = step

    def update_observation(self, observation: dict[str, Any], *, step: int) -> None:
        self.begin_step(step)
        previous_signature = self.last_observation.get(
            "content_sha256"
        ) or self.last_observation.get("screenshot_sha256")
        current_signature = observation.get("content_sha256") or observation.get(
            "screenshot_sha256"
        )
        screen_changed: bool | None = None
        if (
            isinstance(previous_signature, str)
            and previous_signature
            and isinstance(current_signature, str)
            and current_signature
        ):
            screen_changed = previous_signature != current_signature
            self.stagnant_observation_count = (
                0 if screen_changed else self.stagnant_observation_count + 1
            )
        payload = deepcopy(observation)
        payload["screen_changed_since_previous"] = screen_changed
        payload["screen_change_basis"] = (
            "content_sha256" if observation.get("content_sha256") else "screenshot_sha256"
        )
        payload["stagnant_observation_count"] = self.stagnant_observation_count
        self.last_observation = payload
        self.current_app = str(payload.get("current_app", ""))

    def update_action(
        self, action: dict[str, Any], *, step: int, signature: str, coordinate_signature: str = ""
    ) -> None:
        self.begin_step(step)
        if not signature:
            self.repeated_action_count = 0
        elif signature == self.last_action_signature:
            self.repeated_action_count += 1
        else:
            self.repeated_action_count = 1
        self.last_action_signature = signature
        if not coordinate_signature:
            self.repeated_coordinate_count = 0
        elif coordinate_signature == self.last_coordinate_signature:
            self.repeated_coordinate_count += 1
        else:
            self.repeated_coordinate_count = 1
        self.last_coordinate_signature = coordinate_signature
        if action.get("_metadata") == "do" and action.get("action") == "Launch":
            self.target_app = str(action.get("app", "")).strip()

    def update_execution(
        self,
        *,
        success: bool,
        should_finish: bool,
        message: str | None,
        action: dict[str, Any] | None,
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
        command_success: bool | None = None,
    ) -> None:
        self.last_execution = {
            "success": success,
            "command_success": command_success,
            "should_finish": should_finish,
            "message": message,
            "action": deepcopy(action),
            "error_code": error_code,
            "metadata": deepcopy(metadata or {}),
            "verification": {},
            "recovery": {},
        }
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            if message:
                self.add_failure(message)

    def update_verification(self, verification: dict[str, Any]) -> None:
        """Attach verification evidence to the latest execution."""
        if not self.last_execution:
            raise StateTransitionError("Cannot update verification before execution")
        self.last_execution["verification"] = deepcopy(verification)

    def update_recovery(self, recovery: dict[str, Any]) -> None:
        """Attach a recovery outcome to the latest execution."""
        if not self.last_execution:
            raise StateTransitionError("Cannot update recovery before execution")
        self.recovery_count += 1
        self.last_execution["recovery"] = deepcopy(recovery)

    def add_failure(self, reason: str) -> None:
        if not reason:
            return
        self.failures.append(reason)
        if len(self.failures) > 100:
            del self.failures[:-100]

    def finish(self, *, success: bool, message: str | None) -> dict[str, Any] | None:
        """Enter the completed or failed phase and store the final result."""
        target = AgentPhase.COMPLETED if success else AgentPhase.FAILED
        transition = self._apply_transition(target, reason=message or "Task finalized")
        self.success = success
        self.final_message = message or ""
        self.finished_at = time.time()
        return transition

    def cancel(self, *, message: str | None) -> dict[str, Any] | None:
        """Enter the cancelled phase and store the final result."""
        transition = self._apply_transition(
            AgentPhase.CANCELLED,
            reason=message or "Task cancelled",
        )
        self.success = False
        self.final_message = message or ""
        self.finished_at = time.time()
        return transition

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(
            {
                "goal": self.goal,
                "phase": self.phase.value,
                "current_step": self.current_step,
                "current_app": self.current_app,
                "target_app": self.target_app,
                "last_observation": self.last_observation,
                "last_action_signature": self.last_action_signature,
                "last_coordinate_signature": self.last_coordinate_signature,
                "repeated_action_count": self.repeated_action_count,
                "repeated_coordinate_count": self.repeated_coordinate_count,
                "stagnant_observation_count": self.stagnant_observation_count,
                "last_execution": self.last_execution,
                "failures": list(self.failures),
                "consecutive_failures": self.consecutive_failures,
                "recovery_count": self.recovery_count,
                "finished": self.finished,
                "success": self.success,
                "final_message": self.final_message,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }
        )
