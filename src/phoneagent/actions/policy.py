"""Side-effect-free action execution policies."""

from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEYWORDS = (
    "支付",
    "付款",
    "转账",
    "提现",
    "购买",
    "下单",
    "提交订单",
    "确认订单",
    "确认支付",
    "发送",
    "发布",
    "评论",
    "点赞",
    "关注",
    "订阅",
    "保存",
    "提交",
    "删除",
    "清空",
    "注销",
    "安装",
    "卸载",
    "授权",
    "允许",
    "同意",
    "退款",
    "挂号",
    "预约",
    "拨打",
    "拨出",
    "呼叫",
    "pay",
    "purchase",
    "place order",
    "send",
    "post",
    "publish",
    "delete",
    "clear",
    "authorize",
    "allow",
    "confirm order",
)
_POLICY_TEXT_FIELDS = ("label", "description", "instruction", "message", "target")
_COORDINATE_ACTIONS = {"Tap", "Double Tap", "Long Press", "Swipe"}
_TASK_SCOPE_ACTIONS = _COORDINATE_ACTIONS | {"Call_API"}

# These expressions classify only high-consequence user tasks, not the
# model-authored action.  Ordinary communication, deletion, and reversible
# device-setting changes are intentionally excluded from the expensive visual
# risk-review path.  Deterministic action-level confirmation still applies when
# the proposed action itself is explicitly described or marked as sensitive.
#
# The expressions describe operations rather than application names; for
# example, simply opening Alipay or a banking app is not payment authorization.
_TASK_RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "financial_or_commercial",
        re.compile(
            r"支付(?!宝|密码)|付款|转账|提现|汇款|充值|收款|购买|下单|退款|"
            r"提交订单|确认订单|确认支付|贷款|借款|还款|申购|赎回|买入|卖出|"
            r"\bpay\b|purchase|place\s+an?\s+order|transfer|withdraw|refund|"
            r"remit|deposit|loan|repay|buy|sell",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_or_account_security",
        re.compile(
            r"密码|验证码|动态码|校验码|口令|密钥|私钥|助记词|恢复短语|"
            r"(?:PIN|OTP)(?:码)?|二次验证|双重验证|两步验证|"
            r"(?:注销|删除).{0,8}(?:账号|账户)|绑定银行卡|解绑银行卡|"
            r"password|passcode|verification\s+code|one[-\s]?time\s+password|"
            r"private\s+key|seed\s+phrase|recovery\s+phrase|"
            r"(?:delete|close)\s+(?:an?\s+)?account",
            re.IGNORECASE,
        ),
    ),
)

_NEGATIVE_TASK_BOUNDARY_RE = re.compile(
    r"(?:不要|不得|禁止|切勿|无需|不允许).{0,18}"
    r"(?:发送|发布|支付|付款|转账|购买|下单|提交|保存|确认|授权|允许|拨打|拨出|"
    r"删除|清空|修改|改变|开启|开始|扫描|上传|登录)|"
    r"停留在.{0,24}(?:前|页面)|"
    r"\b(?:do\s+not|don't|must\s+not|without)\b.{0,40}"
    r"(?:send|post|pay|purchase|order|submit|save|confirm|authorize|call|delete|modify)",
    re.IGNORECASE,
)


def task_risk_reasons(task: str) -> tuple[str, ...]:
    """Return stable risk categories inferred from the user-authored task."""
    text = str(task or "").strip()
    if not text:
        return ()
    return tuple(name for name, pattern in _TASK_RISK_PATTERNS if pattern.search(text))


def task_has_negative_boundary(task: str) -> bool:
    """Whether the task explicitly says that a consequential step must not occur."""
    return bool(_NEGATIVE_TASK_BOUNDARY_RE.search(str(task or "")))


def action_needs_task_risk_review(action: dict[str, Any], task: str) -> bool:
    """Whether a screenshot-bound action needs an independent scope review."""
    return bool(
        action.get("_metadata") == "do"
        and str(action.get("action", "")) in _COORDINATE_ACTIONS
        and (task_risk_reasons(task) or task_has_negative_boundary(task))
    )


def action_text(action: dict[str, Any]) -> str:
    """Collect model-authored semantic labels used by the deterministic policy."""
    return " ".join(str(action.get(field, "")) for field in _POLICY_TEXT_FIELDS).strip()


def _contains_sensitive_keyword(text: str) -> bool:
    # An application name is not itself an authorization to perform the
    # similarly named operation.
    normalized = text.casefold().replace("支付宝", "")
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def task_scope_violation_message(action: dict[str, Any], task: str) -> str | None:
    """Block an explicitly described final action that contradicts a task boundary.

    This is deliberately limited to actions that can directly produce an external
    side effect. Vague or unlabeled coordinate actions are sent to the visual risk
    reviewer instead of being guessed safe here.
    """
    if not task_has_negative_boundary(task):
        return None
    if (
        action.get("_metadata") != "do"
        or str(action.get("action", "")) not in _TASK_SCOPE_ACTIONS
    ):
        return None
    described_effect = action_text(action)
    if not described_effect:
        return None
    if _contains_sensitive_keyword(described_effect):
        return (
            "The proposed action appears to cross an explicit user boundary: "
            f"{described_effect}"
        )
    return None


def confirmation_message(
    action: dict[str, Any],
    *,
    task: str = "",
    task_risk_checked: bool = False,
) -> str | None:
    """Return a confirmation prompt for actions with external side effects."""
    if action.get("sensitive") is True or action.get("requires_confirmation") is True:
        return str(
            action.get("message")
            or action.get("description")
            or "This action was marked as sensitive by the model."
        )
    if action.get("risk_level") == "high":
        return str(
            action.get("description")
            or action.get("message")
            or "High-risk action requires confirmation."
        )

    haystack = action_text(action)
    if haystack and _contains_sensitive_keyword(haystack):
        return f"Sensitive operation detected: {haystack}"
    reasons = task_risk_reasons(task)
    negative_boundary = task_has_negative_boundary(task)
    if (
        (reasons or negative_boundary)
        and not task_risk_checked
        and action.get("_metadata") == "do"
        and str(action.get("action", "")) in _COORDINATE_ACTIONS
    ):
        task_context = (
            "was classified as potentially consequential "
            f"({', '.join(reasons)})"
            if reasons
            else "contains an explicit negative task boundary"
        )
        return (
            "Task-aware confirmation required for this coordinate action because the user "
            f"task {task_context}."
        )
    return None


def parse_duration_seconds(duration: str | int | float) -> float:
    """Parse a bounded-wait duration value into non-negative seconds."""
    if isinstance(duration, bool):
        return 1.0
    if isinstance(duration, (int, float)):
        return max(0.0, float(duration))
    text = str(duration).strip().casefold()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 1.0
    value = max(0.0, float(match.group(0)))
    if any(unit in text for unit in ("millisecond", "milliseconds", "ms", "毫秒")):
        return value / 1000.0
    if any(unit in text for unit in ("minute", "minutes", "min", "分钟")):
        return value * 60.0
    return value
