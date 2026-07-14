"""Runtime state abstraction for long-running GUI tasks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from phoneagent.runtime.state_machine import AgentPhase, TaskStateMachine


@dataclass(slots=True)
class AgentState:
    """Working memory and lifecycle state of the current GUI task."""

    goal: str = ""
    current_step: int = 0
    subgoal: str = ""
    current_app: str = ""
    target_app: str = ""
    last_observation: dict[str, Any] = field(default_factory=dict)
    last_thinking: str = ""
    last_model_output: str = ""
    last_action: dict[str, Any] | None = None
    last_action_signature: str = ""
    repeated_action_count: int = 0
    stagnant_observation_count: int = 0
    last_execution: dict[str, Any] = field(default_factory=dict)
    last_verification: dict[str, Any] = field(default_factory=dict)
    last_recovery: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    recovery_count: int = 0
    finished: bool = False
    success: bool | None = None
    final_message: str = ""
    started_at: float | None = None
    finished_at: float | None = None
    machine: TaskStateMachine = field(default_factory=TaskStateMachine)

    @property
    def phase(self) -> AgentPhase:
        return self.machine.phase

    def reset(self) -> None:
        self.goal = ""
        self.current_step = 0
        self.subgoal = ""
        self.current_app = ""
        self.target_app = ""
        self.last_observation.clear()
        self.last_thinking = ""
        self.last_model_output = ""
        self.last_action = None
        self.last_action_signature = ""
        self.repeated_action_count = 0
        self.stagnant_observation_count = 0
        self.last_execution.clear()
        self.last_verification.clear()
        self.last_recovery.clear()
        self.failures.clear()
        self.consecutive_failures = 0
        self.recovery_count = 0
        self.finished = False
        self.success = None
        self.final_message = ""
        self.started_at = None
        self.finished_at = None
        self.machine.reset()

    def start(self, goal: str) -> None:
        self.reset()
        self.goal = goal
        self.started_at = time.time()

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
            if screen_changed:
                self.stagnant_observation_count = 0
            else:
                self.stagnant_observation_count += 1
        observation = dict(observation)
        observation["screen_changed_since_previous"] = screen_changed
        observation["stagnant_observation_count"] = self.stagnant_observation_count
        self.last_observation = observation
        self.current_app = str(observation.get("current_app", ""))

    def update_model_response(self, *, thinking: str, raw_content: str) -> None:
        self.last_thinking = thinking
        self.last_model_output = raw_content

    def update_action(
        self,
        action: dict[str, Any],
        *,
        step: int,
        signature: str,
    ) -> None:
        self.begin_step(step)
        if signature and signature == self.last_action_signature:
            self.repeated_action_count += 1
        else:
            self.repeated_action_count = 1
        self.last_action_signature = signature
        self.last_action = dict(action)
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
        if verification is not None:
            self.last_verification = dict(verification)
        if recovery is not None:
            self.last_recovery = dict(recovery)
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            if message:
                self.add_failure(message)

    def update_recovery(self, recovery: dict[str, Any]) -> None:
        self.last_recovery = dict(recovery)
        self.recovery_count += 1
        if self.last_execution:
            self.last_execution["recovery"] = dict(recovery)

    def add_failure(self, reason: str) -> None:
        if reason:
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
            "current_step": self.current_step,
            "subgoal": self.subgoal,
            "current_app": self.current_app,
            "target_app": self.target_app,
            "phase": self.phase.value,
            "state_machine": self.machine.to_dict(),
            "last_observation": self.last_observation,
            "last_thinking": self.last_thinking,
            "last_model_output": self.last_model_output,
            "last_action": self.last_action,
            "last_action_signature": self.last_action_signature,
            "repeated_action_count": self.repeated_action_count,
            "stagnant_observation_count": self.stagnant_observation_count,
            "last_execution": self.last_execution,
            "last_verification": self.last_verification,
            "last_recovery": self.last_recovery,
            "failures": list(self.failures),
            "consecutive_failures": self.consecutive_failures,
            "recovery_count": self.recovery_count,
            "finished": self.finished,
            "success": self.success,
            "final_message": self.final_message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
