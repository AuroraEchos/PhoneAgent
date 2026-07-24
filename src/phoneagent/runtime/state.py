"""Single-source runtime state for one PhoneAgent task."""

from __future__ import annotations

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
    repeated_action_count: int = 0
    stagnant_observation_count: int = 0
    last_execution: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    recovery_count: int = 0
    finished: bool = False
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
        self.repeated_action_count = 0
        self.stagnant_observation_count = 0
        self.last_execution.clear()
        self.failures.clear()
        self.consecutive_failures = 0
        self.recovery_count = 0
        self.finished = False
        self.success = None
        self.final_message = ""
        self.started_at = None
        self.finished_at = None

    def start(self, goal: str) -> None:
        self.reset()
        self.goal = goal
        self.started_at = time.time()

    def transition(
        self,
        target: AgentPhase,
        *,
        reason: str = "",
        step: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Validate and apply one phase transition.

        The returned payload is recorded directly as a trajectory event; no
        second in-memory transition history is retained.
        """
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
            "step": step,
            "metadata": dict(metadata or {}),
            "timestamp": time.time(),
        }

    def begin_step(self, step: int) -> None:
        self.current_step = max(0, step)

    def update_observation(self, observation: dict[str, Any], *, step: int) -> None:
        self.begin_step(step)
        previous_signature = str(self.last_observation.get("screenshot_sha256", ""))
        current_signature = str(observation.get("screenshot_sha256", ""))
        screen_changed = bool(
            previous_signature and current_signature and previous_signature != current_signature
        )
        if previous_signature and current_signature:
            self.stagnant_observation_count = (
                0 if screen_changed else self.stagnant_observation_count + 1
            )
        payload = dict(observation)
        payload["screen_changed_since_previous"] = screen_changed
        payload["stagnant_observation_count"] = self.stagnant_observation_count
        self.last_observation = payload
        self.current_app = str(payload.get("current_app", ""))

    def update_action(self, action: dict[str, Any], *, step: int, signature: str) -> None:
        self.begin_step(step)
        self.repeated_action_count = (
            self.repeated_action_count + 1
            if signature and signature == self.last_action_signature
            else 1
        )
        self.last_action_signature = signature
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
        verification: dict[str, Any] | None = None,
        recovery: dict[str, Any] | None = None,
    ) -> None:
        self.last_execution = {
            "success": success,
            "command_success": success if command_success is None else command_success,
            "should_finish": should_finish,
            "message": message,
            "action": action,
            "error_code": error_code,
            "metadata": metadata or {},
            "verification": verification or {},
            "recovery": recovery or {},
        }
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            if message:
                self.add_failure(message)

    def update_recovery(self, recovery: dict[str, Any]) -> None:
        self.recovery_count += 1
        if self.last_execution:
            self.last_execution["recovery"] = dict(recovery)

    def add_failure(self, reason: str) -> None:
        if not reason:
            return
        self.failures.append(reason)
        if len(self.failures) > 100:
            del self.failures[:-100]

    def finish(self, *, success: bool, message: str | None) -> None:
        self.finished = True
        self.success = success
        self.final_message = message or ""
        self.finished_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "phase": self.phase.value,
            "current_step": self.current_step,
            "current_app": self.current_app,
            "target_app": self.target_app,
            "last_observation": self.last_observation,
            "last_action_signature": self.last_action_signature,
            "repeated_action_count": self.repeated_action_count,
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
