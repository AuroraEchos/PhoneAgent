"""Runtime event definitions shared by callbacks and trajectory persistence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """High-level events emitted by the agent runtime."""

    START = "start"
    PHASE_CHANGE = "phase_change"
    OBSERVATION = "observation"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    PROTOCOL_RETRY = "protocol_retry"
    THINKING = "thinking"
    ACTION = "action"
    PRECONDITION = "precondition"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    FINISH = "finish"
    ERROR = "error"
    METRICS = "metrics"


@dataclass(slots=True)
class AgentEvent:
    """One immutable-in-practice runtime event.

    The same event instance is sent to callbacks and serialized into the run
    trajectory, preventing timestamp or payload drift between two histories.
    """

    type: EventType
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    step: int | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "timestamp": self.timestamp,
            "type": self.type.value,
            "message": self.message,
            "payload": dict(self.payload),
        }
        if self.step is not None:
            data["step"] = self.step
        return data
