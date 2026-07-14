"""Bounded and safety-aware recovery policy for PhoneAgent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from phoneagent.runtime.verification import VerificationResult


class RecoveryStrategy(str, Enum):
    NONE = "none"
    REPLAN = "replan"
    REOBSERVE = "reobserve"
    RETRY_ACTION = "retry_action"
    BACKTRACK = "backtrack"
    RELAUNCH = "relaunch"
    HOME_RESET = "home_reset"
    TAKEOVER = "takeover"
    ABORT = "abort"


@dataclass(slots=True)
class RecoveryConfig:
    """Limits and opt-ins for automatic recovery behavior."""

    enabled: bool = True
    max_total_recoveries: int = 8
    max_attempts_per_failure: int = 2
    retry_delay_seconds: float = 0.35
    allow_safe_action_retry: bool = True
    allow_relaunch: bool = True
    allow_backtrack: bool = False
    allow_home_reset: bool = False
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
    """Choose deterministic recovery without replaying risky side effects."""

    _NON_RETRYABLE_ERRORS = {
        "user_cancelled",
        "invalid_action",
        "app_not_found",
        "app_not_installed",
        "app_not_discovered",
        "app_name_ambiguous",
        "package_not_launchable",
        "launcher_search_failed",
        "launcher_search_not_observed",
        "verification_inconclusive",
        "api_callback_not_configured",
        "empty_api_instruction",
        "empty_note",
    }
    _OBSERVATION_ERRORS = {
        "observation_failed",
        "screenshot_unavailable",
        "verification_observation_failed",
        "device_unavailable",
    }
    _PROTECTED_SCREEN_ERRORS = {"protected_or_blank_screen"}
    _MODEL_PROTOCOL_ERRORS = {"action_parse_error", "model_output_truncated"}
    _SAFE_RETRY_ACTIONS = {"Launch", "Wait", "Home"}

    def __init__(self, config: RecoveryConfig | None = None):
        self.config = config or RecoveryConfig()
        self.total_recoveries = 0
        self.attempts: dict[str, int] = {}

    def reset(self) -> None:
        self.total_recoveries = 0
        self.attempts.clear()

    def mark_success(self) -> None:
        """End the current failure episode after a verified/accepted step.

        Per-failure retry counts describe consecutive recovery attempts. They
        must not accumulate across unrelated failures later in a long task.
        The task-level ``total_recoveries`` budget remains unchanged.
        """
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
        if (
            self.config.max_total_recoveries > 0
            and self.total_recoveries > self.config.max_total_recoveries
        ):
            return self._decision(
                RecoveryStrategy.ABORT,
                "Total recovery budget was exhausted",
                failure_key,
                attempt,
                terminal=True,
            )
        if (
            self.config.max_attempts_per_failure > 0
            and attempt > self.config.max_attempts_per_failure
        ):
            return self._decision(
                RecoveryStrategy.ABORT,
                f"Recovery attempts exhausted for {failure_key}",
                failure_key,
                attempt,
                terminal=True,
            )

        if context.error_code in self._NON_RETRYABLE_ERRORS:
            if context.error_code == "user_cancelled":
                return self._decision(
                    RecoveryStrategy.ABORT,
                    "User cancellation is terminal and must never be overridden",
                    failure_key,
                    attempt,
                    terminal=True,
                )
            return self._decision(
                RecoveryStrategy.REPLAN,
                "The failure requires a different model strategy, not command replay",
                failure_key,
                attempt,
            )

        if context.error_code in self._PROTECTED_SCREEN_ERRORS:
            if self.config.allow_takeover:
                return self._decision(
                    RecoveryStrategy.TAKEOVER,
                    "The screen is protected or blank; manual takeover is required",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.ABORT,
                "Protected screen cannot be recovered automatically",
                failure_key,
                attempt,
                terminal=True,
            )

        if context.error_code in self._OBSERVATION_ERRORS:
            return self._decision(
                RecoveryStrategy.REOBSERVE,
                "Acquire a fresh trusted observation before making another decision",
                failure_key,
                attempt,
            )

        if context.error_code in self._MODEL_PROTOCOL_ERRORS:
            return self._decision(
                RecoveryStrategy.REPLAN,
                "Retry once with a compact strict-action prompt and no malformed output history",
                failure_key,
                attempt,
            )

        if context.error_code == "verification_app_mismatch":
            if action_name == "Launch" and self.config.allow_relaunch and attempt == 1:
                return self._decision(
                    RecoveryStrategy.RELAUNCH,
                    "The requested application is not foreground; relaunch it once",
                    failure_key,
                    attempt,
                )
            if (
                self.config.allow_home_reset
                and context.consecutive_failures >= 2
                and context.target_app
            ):
                return self._decision(
                    RecoveryStrategy.HOME_RESET,
                    "Relaunch did not restore the foreground app; reset navigation at Home",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.REOBSERVE,
                "Foreground app mismatch requires a fresh observation",
                failure_key,
                attempt,
            )

        if context.error_code in {"verification_no_effect", "verification_home_failed"}:
            if (
                self._safe_to_retry(context.action)
                and self.config.allow_safe_action_retry
                and attempt == 1
            ):
                return self._decision(
                    RecoveryStrategy.RETRY_ACTION,
                    "The action is idempotent enough for one bounded retry",
                    failure_key,
                    attempt,
                )
            if self.config.allow_backtrack and context.consecutive_failures >= 2:
                return self._decision(
                    RecoveryStrategy.BACKTRACK,
                    "Repeated no-effect navigation failure; return one level",
                    failure_key,
                    attempt,
                )
            if (
                self.config.allow_home_reset
                and context.consecutive_failures >= 3
                and context.target_app
            ):
                return self._decision(
                    RecoveryStrategy.HOME_RESET,
                    "Repeated no-effect failures reached the Home-reset threshold",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.REPLAN,
                "Do not replay a potentially side-effecting action; ask the model to replan",
                failure_key,
                attempt,
            )

        if context.error_code == "launch_command_failed":
            if (
                action_name == "Launch"
                and self.config.allow_safe_action_retry
                and attempt == 1
            ):
                return self._decision(
                    RecoveryStrategy.RETRY_ACTION,
                    "Direct package launch failed; retry once after catalog resolution",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.REPLAN,
                "Application launch command failed after the bounded retry",
                failure_key,
                attempt,
            )

        if context.error_code in {"action_execution_failed", "repeated_action_blocked"}:
            if (
                self._safe_to_retry(context.action)
                and self.config.allow_safe_action_retry
                and attempt == 1
            ):
                return self._decision(
                    RecoveryStrategy.RETRY_ACTION,
                    "Retry a bounded idempotent action after transport/execution failure",
                    failure_key,
                    attempt,
                )
            if (
                self.config.allow_home_reset
                and context.consecutive_failures >= 3
                and context.target_app
            ):
                return self._decision(
                    RecoveryStrategy.HOME_RESET,
                    "Repeated execution failures reached the Home-reset threshold",
                    failure_key,
                    attempt,
                )
            return self._decision(
                RecoveryStrategy.REOBSERVE,
                "Reobserve and choose a different action instead of blind replay",
                failure_key,
                attempt,
            )

        if (
            self.config.allow_home_reset
            and context.consecutive_failures >= 3
            and context.target_app
        ):
            return self._decision(
                RecoveryStrategy.HOME_RESET,
                "Repeated failures reached the configured home-reset threshold",
                failure_key,
                attempt,
            )

        return self._decision(
            RecoveryStrategy.REPLAN,
            "Expose structured failure evidence to the model for a new plan",
            failure_key,
            attempt,
        )

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
