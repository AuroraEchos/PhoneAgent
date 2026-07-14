"""Explicit task-level state machine for PhoneAgent."""

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
class PhaseTransition:
    """One auditable phase transition."""

    previous: AgentPhase
    current: AgentPhase
    reason: str = ""
    step: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous": self.previous.value,
            "current": self.current.value,
            "reason": self.reason,
            "step": self.step,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class TaskStateMachine:
    """Small deterministic state machine with a bounded audit history."""

    phase: AgentPhase = AgentPhase.IDLE
    history: list[PhaseTransition] = field(default_factory=list)
    max_history: int = 256

    def reset(self) -> None:
        self.phase = AgentPhase.IDLE
        self.history.clear()

    def transition(
        self,
        target: AgentPhase,
        *,
        reason: str = "",
        step: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PhaseTransition | None:
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
        transition = PhaseTransition(
            previous=self.phase,
            current=target,
            reason=reason,
            step=step,
            metadata=dict(metadata or {}),
        )
        self.phase = target
        self.history.append(transition)
        if len(self.history) > self.max_history:
            del self.history[:-self.max_history]
        return transition

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "terminal": self.phase.terminal,
            "history": [item.to_dict() for item in self.history],
        }
