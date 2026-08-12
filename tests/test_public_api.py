from __future__ import annotations


def test_v014_public_imports_remain_available_after_refactor() -> None:
    from phoneagent import (
        AgentConfig,
        AgentPhase,
        FreshnessConfig,
        PhoneAgent,
        RecoveryConfig,
        StepResult,
        VerificationConfig,
        __version__,
    )
    from phoneagent.actions import (
        ActionHandler,
        ActionParseError,
        ActionResult,
        do,
        finish,
        parse_action,
        validate_action,
    )
    from phoneagent.actions.handler import (
        ActionParseError as HandlerActionParseError,
    )
    from phoneagent.actions.handler import (
        do as handler_do,
    )
    from phoneagent.model import (
        AsyncOpenAIModelClient,
        BaseModelClient,
        MessageBuilder,
        ModelClient,
        ModelConfig,
        ModelProtocolError,
        ModelRequestCancelled,
        ModelResponse,
        ModelResponseParser,
        OpenAIModelClient,
        StreamingBoundaryDetector,
    )
    from phoneagent.runtime import (
        ActionVerifier,
        AgentEvent,
        AgentState,
        EventType,
        FreshnessResult,
        ObservationFreshnessGuard,
        RecoveryContext,
        RecoveryDecision,
        RecoveryManager,
        RecoveryOutcome,
        RecoveryStrategy,
        StateTransitionError,
        TrajectoryRecorder,
        VerificationResult,
        VerificationStatus,
    )

    exported = (
        AgentConfig,
        AgentPhase,
        FreshnessConfig,
        PhoneAgent,
        RecoveryConfig,
        StepResult,
        VerificationConfig,
        ActionHandler,
        ActionParseError,
        ActionResult,
        do,
        finish,
        parse_action,
        validate_action,
        AsyncOpenAIModelClient,
        BaseModelClient,
        MessageBuilder,
        ModelClient,
        ModelConfig,
        ModelProtocolError,
        ModelRequestCancelled,
        ModelResponse,
        ModelResponseParser,
        OpenAIModelClient,
        StreamingBoundaryDetector,
        ActionVerifier,
        AgentEvent,
        AgentState,
        EventType,
        FreshnessResult,
        ObservationFreshnessGuard,
        RecoveryContext,
        RecoveryDecision,
        RecoveryManager,
        RecoveryOutcome,
        RecoveryStrategy,
        StateTransitionError,
        TrajectoryRecorder,
        VerificationResult,
        VerificationStatus,
    )
    assert all(item is not None for item in exported)
    assert isinstance(__version__, str)
    assert ModelClient is OpenAIModelClient
    assert HandlerActionParseError is ActionParseError
    assert handler_do is do
