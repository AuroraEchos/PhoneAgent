from __future__ import annotations

from phoneagent.actions import do
from phoneagent.runtime import (
    RecoveryConfig,
    RecoveryContext,
    RecoveryManager,
    RecoveryStrategy,
)


def context(action_name: str, error_code: str = "verification_no_effect") -> RecoveryContext:
    return RecoveryContext(
        error_code=error_code,
        message="failed",
        action=do(action=action_name),
        consecutive_failures=1,
        repeated_action_count=1,
        current_app="Example",
    )


def test_back_is_never_blindly_retried() -> None:
    manager = RecoveryManager(
        RecoveryConfig(max_attempts_per_failure=2, retry_delay_seconds=0)
    )
    decision = manager.decide(context("Back"))
    assert decision.strategy is RecoveryStrategy.REPLAN


def test_home_may_receive_one_bounded_retry() -> None:
    manager = RecoveryManager(
        RecoveryConfig(max_attempts_per_failure=2, retry_delay_seconds=0)
    )
    decision = manager.decide(context("Home", "verification_home_failed"))
    assert decision.strategy is RecoveryStrategy.RETRY_ACTION


def test_success_ends_failure_episode() -> None:
    manager = RecoveryManager(
        RecoveryConfig(max_attempts_per_failure=1, retry_delay_seconds=0)
    )
    first = manager.decide(context("Tap"))
    assert first.attempt == 1
    manager.mark_success()
    second = manager.decide(context("Tap"))
    assert second.attempt == 1
    assert manager.total_recoveries == 2
