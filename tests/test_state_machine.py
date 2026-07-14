from __future__ import annotations

import pytest

from phoneagent.runtime import AgentPhase, StateTransitionError, TaskStateMachine


def test_valid_runtime_path() -> None:
    machine = TaskStateMachine()
    machine.transition(AgentPhase.INITIALIZING)
    machine.transition(AgentPhase.OBSERVING)
    machine.transition(AgentPhase.PLANNING)
    machine.transition(AgentPhase.EXECUTING)
    machine.transition(AgentPhase.VERIFYING)
    machine.transition(AgentPhase.COMPLETED)
    assert machine.phase is AgentPhase.COMPLETED


def test_illegal_transition_is_rejected() -> None:
    machine = TaskStateMachine()
    with pytest.raises(StateTransitionError):
        machine.transition(AgentPhase.EXECUTING)
