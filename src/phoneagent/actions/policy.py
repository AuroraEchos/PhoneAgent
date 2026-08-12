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
    "删除",
    "清空",
    "注销",
    "授权",
    "允许",
    "同意",
    "退款",
    "挂号",
    "预约",
    "拨打",
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


def confirmation_message(action: dict[str, Any]) -> str | None:
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

    haystack = " ".join(str(action.get(field, "")) for field in _POLICY_TEXT_FIELDS).strip()
    if haystack and any(keyword in haystack.casefold() for keyword in _SENSITIVE_KEYWORDS):
        return f"Sensitive operation detected: {haystack}"
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
