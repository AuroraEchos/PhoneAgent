"""Runtime event definitions for PhoneAgent."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """High-level events emitted by the agent runtime."""

    START = "start"
    PHASE_CHANGE = "phase_change"
    APP_CATALOG = "app_catalog"
    OBSERVATION = "observation"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    THINKING = "thinking"
    ACTION = "action"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    FINISH = "finish"
    ERROR = "error"
    METRICS = "metrics"


@dataclass(slots=True)
class AgentEvent:
    """A structured event produced by the agent runtime."""

    type: EventType
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
