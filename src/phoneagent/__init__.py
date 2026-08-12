"""PhoneAgent public API.

Importing :mod:`phoneagent` is intentionally side-effect free. In particular,
it does not load ``.env`` files, inspect ADB devices, or initialize model clients.
The command-line entry point loads local environment configuration explicitly.
"""

from __future__ import annotations

from typing import Any

from phoneagent._version import __version__

__all__ = [
    "__version__",
    "AgentConfig",
    "AgentPhase",
    "FreshnessConfig",
    "PhoneAgent",
    "RecoveryConfig",
    "StepResult",
    "VerificationConfig",
]


def __getattr__(name: str) -> Any:
    """Lazily expose the small programmatic API without import-time side effects."""
    if name in {"AgentConfig", "PhoneAgent", "StepResult"}:
        from phoneagent.agent import AgentConfig, PhoneAgent, StepResult

        return {
            "AgentConfig": AgentConfig,
            "PhoneAgent": PhoneAgent,
            "StepResult": StepResult,
        }[name]
    if name in {"AgentPhase", "FreshnessConfig", "RecoveryConfig", "VerificationConfig"}:
        from phoneagent.runtime import (
            AgentPhase,
            FreshnessConfig,
            RecoveryConfig,
            VerificationConfig,
        )

        return {
            "AgentPhase": AgentPhase,
            "FreshnessConfig": FreshnessConfig,
            "RecoveryConfig": RecoveryConfig,
            "VerificationConfig": VerificationConfig,
        }[name]
    raise AttributeError(f"module 'phoneagent' has no attribute {name!r}")
