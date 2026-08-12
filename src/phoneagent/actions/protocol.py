"""Strict, side-effect-free model action protocol."""

from __future__ import annotations

import ast
import math
import re
from typing import Any

from phoneagent.actions.compatibility import normalize_provider_action_syntax


class ActionParseError(ValueError):
    """Raised when a model action cannot be parsed or validated safely."""


_ACTION_ALIASES = {
    "launch": "Launch",
    "tap": "Tap",
    "type": "Type",
    "type_name": "Type",
    "typename": "Type",
    "swipe": "Swipe",
    "back": "Back",
    "home": "Home",
    "open notifications": "OpenNotifications",
    "open_notifications": "OpenNotifications",
    "opennotifications": "OpenNotifications",
    "open quick settings": "OpenQuickSettings",
    "open_quick_settings": "OpenQuickSettings",
    "openquicksettings": "OpenQuickSettings",
    "close system panel": "CloseSystemPanel",
    "close_system_panel": "CloseSystemPanel",
    "closesystempanel": "CloseSystemPanel",
    "double tap": "Double Tap",
    "double_tap": "Double Tap",
    "doubletap": "Double Tap",
    "long press": "Long Press",
    "long_press": "Long Press",
    "longpress": "Long Press",
    "wait": "Wait",
    "take_over": "Take_over",
    "takeover": "Take_over",
    "interact": "Interact",
    "note": "Note",
    "call_api": "Call_API",
    "callapi": "Call_API",
}

_COORDINATE_ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "Tap": ("element",),
    "Double Tap": ("element",),
    "Long Press": ("element",),
    "Swipe": ("start", "end"),
}

_COMMON_ACTION_FIELDS = {
    "description",
    "message",
    "sensitive",
    "requires_confirmation",
    "risk_level",
}
_ACTION_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "Launch": frozenset({"app"}),
    "Tap": frozenset({"element"}),
    "Type": frozenset({"text"}),
    "Swipe": frozenset({"start", "end"}),
    "Back": frozenset(),
    "Home": frozenset(),
    "OpenNotifications": frozenset(),
    "OpenQuickSettings": frozenset(),
    "CloseSystemPanel": frozenset(),
    "Double Tap": frozenset({"element"}),
    "Long Press": frozenset({"element"}),
    "Wait": frozenset(),
    "Take_over": frozenset({"message"}),
    "Interact": frozenset({"message"}),
    "Note": frozenset({"message"}),
    "Call_API": frozenset({"instruction"}),
}
_ACTION_SPECIFIC_FIELDS: dict[str, frozenset[str]] = {
    "Launch": frozenset({"app"}),
    "Tap": frozenset({"element"}),
    "Type": frozenset({"text", "clear"}),
    "Swipe": frozenset({"start", "end", "duration_ms"}),
    "Back": frozenset(),
    "Home": frozenset(),
    "OpenNotifications": frozenset(),
    "OpenQuickSettings": frozenset(),
    "CloseSystemPanel": frozenset(),
    "Double Tap": frozenset({"element"}),
    "Long Press": frozenset({"element", "duration_ms"}),
    "Wait": frozenset({"duration"}),
    "Take_over": frozenset(),
    "Interact": frozenset(),
    "Note": frozenset(),
    "Call_API": frozenset({"instruction"}),
}


def do(**kwargs: Any) -> dict[str, Any]:
    """Create a model-style executable action dictionary."""
    return {"_metadata": "do", **kwargs}


def finish(
    message: str = "Task completed",
    *,
    success: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a model-style finish action dictionary."""
    return {"_metadata": "finish", "message": message, "success": success, **kwargs}


def parse_action(response: str) -> dict[str, Any]:
    """Parse exactly one Python-style ``do(...)`` or ``finish(...)`` call.

    Model-response splitting is deliberately handled before this function.
    JSON, Markdown code fences, multiple calls and malformed-string repair are
    rejected so protocol errors enter bounded recovery instead of being
    executed heuristically.
    """
    action_text = _normalize_action_text(response)
    action_text = normalize_provider_action_syntax(action_text)
    call_text = _extract_single_call(action_text)
    if re.match(r"^do\s*\(", call_text):
        return validate_action(_parse_do_call(call_text))
    if re.match(r"^finish\s*\(", call_text):
        return validate_action(_parse_finish_call(call_text))
    raise ActionParseError(f"Unsupported action call: {call_text[:200]}")


def validate_action(action: dict[str, Any]) -> dict[str, Any]:
    """Normalize an action and reject malformed or unsafe values."""
    if not isinstance(action, dict):
        raise ActionParseError("Action payload must be a dictionary")

    normalized = dict(action)
    metadata = normalized.get("_metadata")
    if metadata == "finish":
        unknown = set(normalized) - {"_metadata", "message", "success"}
        if unknown:
            raise ActionParseError(
                "finish(...) contains unsupported keyword(s): "
                + ", ".join(sorted(unknown))
            )
        message = normalized.get("message", "Task completed")
        if not isinstance(message, str):
            message = str(message)
        success = normalized.get("success", True)
        if not isinstance(success, bool):
            raise ActionParseError("finish success must be a boolean")
        normalized["message"] = message.strip() or "Task completed"
        normalized["success"] = success
        return normalized

    if metadata != "do":
        raise ActionParseError(f"Unknown action metadata: {metadata!r}")

    raw_name = normalized.get("action")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ActionParseError("do(...) is missing required string keyword: action")
    canonical = _canonical_action_name(raw_name)
    if canonical is None:
        supported = ", ".join(sorted(set(_ACTION_ALIASES.values())))
        raise ActionParseError(f"Unsupported action {raw_name!r}. Supported: {supported}")
    normalized["action"] = canonical

    allowed = {
        "_metadata",
        "action",
        *_COMMON_ACTION_FIELDS,
        *_ACTION_SPECIFIC_FIELDS[canonical],
    }
    unknown = set(normalized) - allowed
    if unknown:
        raise ActionParseError(
            f"{canonical} contains unsupported keyword(s): " + ", ".join(sorted(unknown))
        )
    missing = _ACTION_REQUIRED_FIELDS[canonical] - set(normalized)
    if missing:
        raise ActionParseError(
            f"{canonical} is missing required keyword(s): " + ", ".join(sorted(missing))
        )

    for field_name in _COORDINATE_ACTION_FIELDS.get(canonical, ()):
        normalized[field_name] = _validate_relative_coordinate(
            normalized.get(field_name), field_name
        )

    if canonical == "Launch":
        app = normalized.get("app")
        if not isinstance(app, str) or not app.strip():
            raise ActionParseError('Launch action requires app="..."')
        normalized["app"] = app.strip()

    elif canonical == "Type":
        text = normalized["text"]
        if not isinstance(text, str):
            text = str(text)
        if len(text) > 20_000:
            raise ActionParseError("Type text exceeds the 20,000 character safety limit")
        normalized["text"] = text
        if "clear" in normalized and not isinstance(normalized["clear"], bool):
            raise ActionParseError("Type clear must be a boolean")

    elif canonical in {"Long Press", "Swipe"} and "duration_ms" in normalized:
        normalized["duration_ms"] = _positive_int(normalized["duration_ms"], "duration_ms")

    elif canonical == "Wait":
        duration = normalized.get("duration", "1 second")
        if not isinstance(duration, (str, int, float)):
            raise ActionParseError("Wait duration must be a number or duration string")

    elif canonical in {"Take_over", "Interact", "Note"}:
        message = normalized.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ActionParseError(f"{canonical} requires a non-empty message")
        normalized["message"] = message.strip()

    elif canonical == "Call_API":
        instruction = normalized.get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ActionParseError("Call_API requires a non-empty instruction")
        normalized["instruction"] = instruction.strip()

    for text_field in ("description", "message"):
        if text_field in normalized and not isinstance(normalized[text_field], str):
            raise ActionParseError(f"{text_field} must be a string")

    for flag in ("sensitive", "requires_confirmation"):
        if flag in normalized and not isinstance(normalized[flag], bool):
            raise ActionParseError(f"{flag} must be a boolean")

    risk_level = normalized.get("risk_level")
    if risk_level is not None:
        risk_level = str(risk_level).strip().lower()
        if risk_level not in {"low", "medium", "high"}:
            raise ActionParseError("risk_level must be low, medium, or high")
        normalized["risk_level"] = risk_level

    return normalized


def _normalize_action_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ActionParseError("Model action is empty")
    if text.startswith("```") or text.endswith("```"):
        raise ActionParseError("Markdown code fences are not part of the action protocol")
    return text


def _extract_single_call(text: str) -> str:
    """Extract one balanced call and reject any extra model output."""
    match = re.match(r"^(?:do|finish)\s*\(", text)
    if not match:
        raise ActionParseError(f"Expected one do(...) or finish(...) call: {text[:200]}")

    depth = 0
    quote: str | None = None
    escaped = False
    end: int | None = None
    for pos, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ActionParseError("Unbalanced action parentheses")
            if depth == 0:
                end = pos + 1
                break
    if quote or end is None or depth != 0:
        raise ActionParseError("Incomplete action call")
    if text[end:].strip():
        raise ActionParseError("Exactly one action call is allowed per model turn")
    return text[:end].strip()


def _parse_do_call(call_text: str) -> dict[str, Any]:
    call = _parse_call_ast(call_text)
    if not isinstance(call.func, ast.Name) or call.func.id != "do":
        raise ActionParseError("Expected do(...) call")
    if call.args:
        raise ActionParseError("Positional arguments are not allowed in do(...)")

    action: dict[str, Any] = {"_metadata": "do"}
    seen: set[str] = set()
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ActionParseError("**kwargs is not allowed in action calls")
        if keyword.arg in seen:
            raise ActionParseError(f"Duplicate action keyword: {keyword.arg}")
        seen.add(keyword.arg)
        try:
            action[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as exc:
            raise ActionParseError(
                f"Action keyword {keyword.arg!r} must be a literal value"
            ) from exc
    return action


def _parse_finish_call(call_text: str) -> dict[str, Any]:
    call = _parse_call_ast(call_text)
    if not isinstance(call.func, ast.Name) or call.func.id != "finish":
        raise ActionParseError("Expected finish(...) call")
    if call.args:
        raise ActionParseError("Positional arguments are not allowed in finish(...)")

    parsed: dict[str, Any] = {
        "_metadata": "finish",
        "message": "Task completed",
        "success": True,
    }
    seen: set[str] = set()
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ActionParseError("**kwargs is not allowed in finish calls")
        if keyword.arg in seen:
            raise ActionParseError(f"Duplicate finish keyword: {keyword.arg}")
        seen.add(keyword.arg)
        try:
            parsed[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as exc:
            raise ActionParseError(
                f"Finish keyword {keyword.arg!r} must be a literal value"
            ) from exc
    return parsed


def _parse_call_ast(call_text: str) -> ast.Call:
    call_text = _escape_raw_newlines_in_quoted_strings(call_text)
    try:
        tree = ast.parse(call_text, mode="eval")
    except SyntaxError as exc:
        raise ActionParseError(f"Invalid Python-style action syntax: {exc}") from exc
    if not isinstance(tree.body, ast.Call):
        raise ActionParseError("Action must be a function call")
    return tree.body


def _escape_raw_newlines_in_quoted_strings(text: str) -> str:
    """Escape only CR/LF characters inside a closed quoted action value."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    for char in text:
        if quote is None:
            output.append(char)
            if char in {'"', "'"}:
                quote = char
            continue

        if escaped:
            output.append(char)
            escaped = False
        elif char == "\\":
            output.append(char)
            escaped = True
        elif char == quote:
            output.append(char)
            quote = None
        elif char == "\r":
            output.append("\\r")
        elif char == "\n":
            output.append("\\n")
        else:
            output.append(char)
    return "".join(output)


def _canonical_action_name(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip().replace("-", "_")).lower()
    return _ACTION_ALIASES.get(normalized)


def _validate_relative_coordinate(value: Any, field_name: str) -> list[float | int]:
    if isinstance(value, dict) and set(value) == {"x", "y"}:
        value = [value["x"], value["y"]]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ActionParseError(f"{field_name} must be a two-element [x, y] coordinate")
    output: list[float | int] = []
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise ActionParseError(f"{field_name} coordinates must be numeric")
        number = float(coordinate)
        if not math.isfinite(number) or number < 0 or number > 999:
            raise ActionParseError(
                f"{field_name} coordinates must be finite values in the 0..999 range"
            )
        output.append(coordinate)
    return output


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ActionParseError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ActionParseError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ActionParseError(f"{name} must be positive")
    return parsed
