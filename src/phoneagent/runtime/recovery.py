"""Minimal bounded recovery policy for the research runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from phoneagent.runtime.verification import VerificationResult


class RecoveryStrategy(str, Enum):
    """Small set of recovery operations with distinct safety semantics."""

    REPLAN = "replan"
    REOBSERVE = "reobserve"
    RETRY_ACTION = "retry_action"
    TAKEOVER = "takeover"
    ABORT = "abort"


@dataclass(slots=True)
class RecoveryConfig:
    """Limits for automatic recovery.

    Navigation resets and implicit relaunch branches were intentionally removed.
    They enlarge the state space and are better expressed as explicit model
    actions after a fresh observation.
    """

    enabled: bool = True
    max_total_recoveries: int = 8
    max_attempts_per_failure: int = 2
    retry_delay_seconds: float = 0.35
    allow_safe_action_retry: bool = True
    allow_takeover: bool = True

    def __post_init__(self) -> None:
        if self.max_total_recoveries < 0:
            raise ValueError("max_total_recoveries cannot be negative")
        if self.max_attempts_per_failure < 0:
            raise ValueError("max_attempts_per_failure cannot be negative")
        if self.retry_delay_seconds < 0:
            raise ValueError("recovery retry_delay_seconds cannot be negative")


@dataclass(slots=True)
class RecoveryContext:
    error_code: str
    message: str
    action: dict[str, Any] | None
    consecutive_failures: int
    repeated_action_count: int
    current_app: str
    target_app: str = ""
    verification: VerificationResult | None = None


@dataclass(slots=True)
class RecoveryDecision:
    strategy: RecoveryStrategy
    reason: str
    failure_key: str
    attempt: int
    terminal: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "reason": self.reason,
            "failure_key": self.failure_key,
            "attempt": self.attempt,
            "terminal": self.terminal,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RecoveryOutcome:
    decision: RecoveryDecision
    success: bool
    message: str
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "success": self.success,
            "message": self.message,
            "error_code": self.error_code,
            "metadata": dict(self.metadata),
        }


class RecoveryManager:
    """Choose one conservative recovery without replaying risky side effects."""

    _NON_RETRYABLE_ERRORS = {
        "user_cancelled",
        "invalid_action",
        "app_not_found",
        "app_not_installed",
        "verification_inconclusive",
        "api_callback_not_configured",
        "empty_api_instruction",
        "empty_note",
        "pre_action_observation_changed",
        "task_scope_violation",
        "task_semantic_verification_failed",
        "task_semantic_verification_inconclusive",
    }
    _OBSERVATION_ERRORS = {
        "observation_failed",
        "screenshot_unavailable",
        "verification_observation_failed",
        "device_unavailable",
        "pre_action_observation_failed",
    }
    _MODEL_PROTOCOL_ERRORS = {
        "action_parse_error",
        "incomplete_action",
        "invalid_action_arguments",
        "legacy_action_envelope",
        "missing_action",
        "model_output_truncated",
        "model_protocol_error",
        "multiple_actions",
        "trailing_content",
    }
    _SAFE_RETRY_ACTIONS = {"Launch", "Wait", "Home"}

    def __init__(self, config: RecoveryConfig | None = None):
        self.config = config or RecoveryConfig()
        self.total_recoveries = 0
        self.attempts: dict[str, int] = {}

    def reset(self) -> None:
        self.total_recoveries = 0
        self.attempts.clear()

    def mark_success(self) -> None:
        """End the current failure episode while preserving the run budget."""
        self.attempts.clear()

    def decide(self, context: RecoveryContext) -> RecoveryDecision:
        action_name = str((context.action or {}).get("action", "none"))
        failure_key = f"{context.error_code}:{action_name}"
        attempt = self.attempts.get(failure_key, 0) + 1
        self.attempts[failure_key] = attempt
        self.total_recoveries += 1

        if not self.config.enabled:
            return self._decision(
                RecoveryStrategy.ABORT,
                "Automatic recovery is disabled",
                failure_key,
                attempt,
                terminal=True,
            )
        if self._budget_exhausted(attempt):
            return self._decision(
                RecoveryStrategy.ABORT,
                "Recovery budget was exhausted",
                failure_key,
                attempt,
                terminal=True,
            )

        code = context.error_code
        if code == "user_cancelled":
            return self._decision(
                RecoveryStrategy.ABORT,
                "User cancellation is terminal and must never be overridden",
                failure_key,
                attempt,
                terminal=True,
            )
        if code in self._NON_RETRYABLE_ERRORS:
            return self._decision(
                RecoveryStrategy.REPLAN,
                "The failure requires a different model strategy, not command replay",
                failure_key,
                attempt,
            )
        if code == "protected_or_blank_screen":
            strategy = (
                RecoveryStrategy.TAKEOVER if self.config.allow_takeover else RecoveryStrategy.ABORT
            )
            return self._decision(
                strategy,
                "The screen is protected or blank; manual takeover is required",
                failure_key,
                attempt,
                terminal=strategy is RecoveryStrategy.ABORT,
            )
        if code in self._OBSERVATION_ERRORS:
            return self._decision(
                RecoveryStrategy.REOBSERVE,
                "Acquire a fresh trusted observation before making another decision",
                failure_key,
                attempt,
            )
        if code in self._MODEL_PROTOCOL_ERRORS:
            return self._decision(
                RecoveryStrategy.REPLAN,
                "Retry with the compact strict-action prompt",
                failure_key,
                attempt,
            )

        if code == "verification_app_mismatch":
            if self._can_retry(context.action, attempt):
                return self._decision(
                    RecoveryStrategy.RETRY_ACTION,
                    "The launch action may be retried once before replanning",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.REOBSERVE,
                "Foreground mismatch requires a fresh observation",
                failure_key,
                attempt,
            )

        if code in {
            "verification_no_effect",
            "verification_home_failed",
            "launch_command_failed",
            "action_execution_failed",
            "repeated_action_blocked",
        }:
            if self._can_retry(context.action, attempt):
                return self._decision(
                    RecoveryStrategy.RETRY_ACTION,
                    "Retry one bounded idempotent action",
                    failure_key,
                    attempt,
                )
            strategy = (
                RecoveryStrategy.REOBSERVE
                if code in {"action_execution_failed", "repeated_action_blocked"}
                else RecoveryStrategy.REPLAN
            )
            return self._decision(
                strategy,
                "Do not replay a potentially side-effecting action",
                failure_key,
                attempt,
            )

        return self._decision(
            RecoveryStrategy.REPLAN,
            "Expose structured failure evidence to the model for a new plan",
            failure_key,
            attempt,
        )

    def _budget_exhausted(self, attempt: int) -> bool:
        total_exhausted = (
            self.config.max_total_recoveries > 0
            and self.total_recoveries > self.config.max_total_recoveries
        )
        failure_exhausted = (
            self.config.max_attempts_per_failure > 0
            and attempt > self.config.max_attempts_per_failure
        )
        return total_exhausted or failure_exhausted

    def _can_retry(self, action: dict[str, Any] | None, attempt: int) -> bool:
        return attempt == 1 and self.config.allow_safe_action_retry and self._safe_to_retry(action)

    @classmethod
    def _safe_to_retry(cls, action: dict[str, Any] | None) -> bool:
        if not action or action.get("_metadata") != "do":
            return False
        if action.get("sensitive") or action.get("requires_confirmation"):
            return False
        if str(action.get("risk_level", "")).lower() == "high":
            return False
        return str(action.get("action")) in cls._SAFE_RETRY_ACTIONS

    @staticmethod
    def _decision(
        strategy: RecoveryStrategy,
        reason: str,
        failure_key: str,
        attempt: int,
        *,
        terminal: bool = False,
    ) -> RecoveryDecision:
        return RecoveryDecision(
            strategy=strategy,
            reason=reason,
            failure_key=failure_key,
            attempt=attempt,
            terminal=terminal,
        )
