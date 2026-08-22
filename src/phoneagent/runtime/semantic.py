"""Isolated visual reviews for task completion and consequential actions.

These reviews are advisory model judgments, not deterministic proof.  Their
runtime value is that planning and review use separate contexts, and that an
inconclusive review fails closed instead of silently authorizing a device
action or accepting the planner's own completion claim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from phoneagent.actions import ActionParseError, parse_action
from phoneagent.devices import ScreenObservation
from phoneagent.model import MessageBuilder, ModelResponse


class ReviewVerdict(str, Enum):
    """Closed set of outcomes returned by an isolated semantic review."""

    PASS = "pass"
    FAIL = "fail"
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCK = "block"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


@dataclass(slots=True)
class SemanticReviewConfig:
    """Bounds for model-backed completion and action-risk reviews."""

    completion_enabled: bool = True
    action_risk_enabled: bool = True
    completion_max_tokens: int = 512
    action_risk_max_tokens: int = 384
    protocol_retries: int = 1
    evidence_event_limit: int = 20

    def __post_init__(self) -> None:
        if self.completion_max_tokens <= 0:
            raise ValueError("completion_max_tokens must be positive")
        if self.action_risk_max_tokens <= 0:
            raise ValueError("action_risk_max_tokens must be positive")
        if self.protocol_retries < 0:
            raise ValueError("semantic review protocol_retries cannot be negative")
        if self.evidence_event_limit < 1:
            raise ValueError("evidence_event_limit must be at least 1")


@dataclass(slots=True)
class SemanticReviewResult:
    """Structured evidence from one isolated model review."""

    verdict: ReviewVerdict
    message: str
    purpose: str
    model_action: str | None = None
    attempts: int = 0
    error_code: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict in {ReviewVerdict.PASS, ReviewVerdict.ALLOW, ReviewVerdict.SKIPPED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "message": self.message,
            "purpose": self.purpose,
            "model_action": self.model_action,
            "attempts": self.attempts,
            "error_code": self.error_code,
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


_COMPLETION_SYSTEM_PROMPT = """你是独立的 Android 任务完成复核器，不参与操作规划。
只根据用户原始目标、当前最新截图、Screen Info 和结构化运行证据判断整个任务是否已经完成。
规划模型提出完成、ADB 命令成功或屏幕发生变化都不能单独证明任务完成。
如果截图或确定性证据不能证明完整目标、页面仍停在中间步骤、结果与目标冲突，或存在任何关键不确定性，必须判定失败。
响应正文只能包含一个 finish(...) 调用：
- 已有充分证据：finish(success=True, message="简洁证据")
- 证据不足或目标未完成：finish(success=False, message="缺失或冲突的证据")
不要输出 do(...)、分析、Markdown、JSON 或调用后的文字。"""


_ACTION_RISK_SYSTEM_PROMPT = """你是独立的 Android 动作风险复核器，不参与任务规划。
根据用户原始目标、其中的禁止边界、最新截图和拟执行坐标动作，判断该动作的直接效果：
动作坐标使用左上角 [0,0]、右下角 [999,999] 的归一化截图坐标。
- ALLOW：只是导航、选择或编辑，当前动作不会提交外部副作用，也不违反用户边界。
- CONFIRM：当前动作可能发送、发布、支付、下单、转账、删除、授权、拨号、预约、保存或提交外部状态，需要用户在执行前确认。
- BLOCK：当前动作会违反“不要发送/不要提交/停留在确认前”等明确用户边界，或明显超出任务范围。
不确定时必须选择 CONFIRM，不能猜测安全。
响应正文只能包含一个 finish(...) 调用：
- ALLOW 使用 finish(success=True, message="ALLOW: 原因")
- CONFIRM 使用 finish(success=False, message="CONFIRM: 原因")
- BLOCK 使用 finish(success=False, message="BLOCK: 原因")
不要输出 do(...)、分析、Markdown、JSON 或调用后的文字。"""


def build_completion_review_context(
    *,
    goal: str,
    proposed_message: str,
    observation: ScreenObservation,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a fresh context that shares no planner conversation history."""
    payload = {
        "user_goal": goal,
        "planner_completion_message": proposed_message,
        "screen_info": observation.to_screen_info(),
        "recent_runtime_evidence": evidence,
    }
    return [
        MessageBuilder.create_system_message(_COMPLETION_SYSTEM_PROMPT),
        MessageBuilder.create_user_message(
            text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            image_base64=observation.screenshot.base64_data,
            image_mime_type=observation.screenshot.mime_type,
        ),
    ]


def build_action_risk_review_context(
    *,
    goal: str,
    action: dict[str, Any],
    observation: ScreenObservation,
    risk_reasons: tuple[str, ...],
    negative_boundary: bool,
) -> list[dict[str, Any]]:
    """Build an isolated visual review for one untrusted planner action."""
    payload = {
        "user_goal": goal,
        "task_risk_categories": list(risk_reasons),
        "explicit_negative_boundary": negative_boundary,
        "proposed_action": action,
        "screen_info": observation.to_screen_info(),
    }
    return [
        MessageBuilder.create_system_message(_ACTION_RISK_SYSTEM_PROMPT),
        MessageBuilder.create_user_message(
            text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            image_base64=observation.screenshot.base64_data,
            image_mime_type=observation.screenshot.mime_type,
        ),
    ]


def parse_completion_review(response: ModelResponse, *, attempts: int) -> SemanticReviewResult:
    """Parse one finish-only completion verdict."""
    try:
        action = parse_action(response.action)
    except ActionParseError as exc:
        raise ActionParseError(f"Invalid completion review: {exc}") from exc
    if action.get("_metadata") != "finish":
        raise ActionParseError("Completion review must return finish(...)")
    success = action.get("success") is True
    message = str(action.get("message") or "").strip()
    return SemanticReviewResult(
        verdict=ReviewVerdict.PASS if success else ReviewVerdict.FAIL,
        message=message or ("Task completion verified" if success else "Task completion rejected"),
        purpose="task_completion",
        model_action=response.action,
        attempts=attempts,
    )


def parse_action_risk_review(response: ModelResponse, *, attempts: int) -> SemanticReviewResult:
    """Parse an ALLOW/CONFIRM/BLOCK verdict encoded in a safe finish call."""
    try:
        action = parse_action(response.action)
    except ActionParseError as exc:
        raise ActionParseError(f"Invalid action risk review: {exc}") from exc
    if action.get("_metadata") != "finish":
        raise ActionParseError("Action risk review must return finish(...)")
    message = str(action.get("message") or "").strip()
    prefix, separator, reason = message.partition(":")
    if not separator:
        prefix, separator, reason = message.partition("：")
    normalized = prefix.strip().casefold()
    mapping = {
        "allow": ReviewVerdict.ALLOW,
        "confirm": ReviewVerdict.CONFIRM,
        "block": ReviewVerdict.BLOCK,
    }
    verdict = mapping.get(normalized)
    if verdict is None:
        raise ActionParseError("Action risk review message must begin with ALLOW:, CONFIRM:, or BLOCK:")
    expected_success = verdict is ReviewVerdict.ALLOW
    if bool(action.get("success")) is not expected_success:
        raise ActionParseError("Action risk review success flag contradicts its verdict")
    return SemanticReviewResult(
        verdict=verdict,
        message=reason.strip() or f"Action risk review returned {verdict.value}",
        purpose="action_risk",
        model_action=response.action,
        attempts=attempts,
    )


def compact_runtime_evidence(
    events: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Keep bounded action/effect evidence without model reasoning or raw output."""
    relevant: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("type", ""))
        if event_type not in {"action", "execution", "verification", "recovery", "precondition"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        item: dict[str, Any] = {
            "type": event_type,
            "step": event.get("step"),
            "message": event.get("message", ""),
        }
        for key in (
            "action",
            "command_success",
            "status",
            "policy",
            "observable_effect_verified",
            "semantic_effect_verified",
            "screen_changed",
            "app_changed",
            "error_code",
            "decision",
            "fresh",
            "reason",
            "source",
        ):
            if key in payload:
                item[key] = payload[key]
        relevant.append(item)
    return relevant[-limit:]
