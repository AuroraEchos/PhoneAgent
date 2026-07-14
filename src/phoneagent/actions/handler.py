"""Safe action parsing, validation and execution for Android PhoneAgent."""

from __future__ import annotations

import ast
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from phoneagent.devices import AndroidDevice


class ActionParseError(ValueError):
    """Raised when a model action cannot be parsed or validated safely."""


@dataclass(slots=True)
class ActionResult:
    """Result of an action execution."""

    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


ConfirmationCallback = Callable[[str], bool]
TakeoverCallback = Callable[[str], None]
NoteCallback = Callable[[str], None]
APICallback = Callable[[str], str | None]


_ACTION_ALIASES = {
    "launch": "Launch",
    "tap": "Tap",
    "type": "Type",
    "type_name": "Type",
    "typename": "Type",
    "swipe": "Swipe",
    "back": "Back",
    "home": "Home",
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
    """Parse and validate one model action.

    Supported protocols:
      * ``do(action="Tap", element=[500, 500])``
      * ``finish(message="done", success=True)``
      * JSON objects containing ``action`` / ``thinking`` fields
      * wrappers such as ``<answer>...</answer>`` and fenced code blocks

    Parsing uses :mod:`ast` and :func:`ast.literal_eval`; model text is never
    evaluated as executable Python.
    """
    action_text = _normalize_action_text(response)
    json_action = _try_parse_action_json(action_text)
    if json_action is not None:
        return validate_action(json_action)

    call_text = _extract_first_call(action_text)
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

    for field_name in _COORDINATE_ACTION_FIELDS.get(canonical, ()):
        normalized[field_name] = _validate_relative_coordinate(
            normalized.get(field_name), field_name
        )

    if canonical == "Launch":
        app = normalized.get("app")
        if not isinstance(app, str) or not app.strip():
            raise ActionParseError("Launch action requires app=\"...\"")
        normalized["app"] = app.strip()

    elif canonical == "Type":
        text = normalized.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        if len(text) > 20_000:
            raise ActionParseError("Type text exceeds the 20,000 character safety limit")
        normalized["text"] = text
        if "clear" in normalized and not isinstance(normalized["clear"], bool):
            raise ActionParseError("Type clear must be a boolean")

    elif canonical in {"Long Press", "Swipe"} and "duration_ms" in normalized:
        normalized["duration_ms"] = _positive_int(
            normalized["duration_ms"], "duration_ms"
        )

    elif canonical == "Wait":
        duration = normalized.get("duration", "1 second")
        if not isinstance(duration, (str, int, float)):
            raise ActionParseError("Wait duration must be a number or duration string")

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
    text = re.sub(r"^```(?:python|json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    answer_match = re.search(r"<answer>(.*?)</answer>", text, flags=re.DOTALL | re.IGNORECASE)
    if answer_match:
        text = answer_match.group(1).strip()
    return text.strip()


def _try_parse_action_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    if payload.get("_metadata") in {"do", "finish"}:
        return payload
    if payload.get("type") == "finish":
        return {
            "_metadata": "finish",
            "message": str(payload.get("message", "Task completed")),
            "success": payload.get("success", True),
        }
    action = payload.get("action")
    if isinstance(action, dict):
        if action.get("type") == "finish" or action.get("_metadata") == "finish":
            return {
                "_metadata": "finish",
                "message": str(action.get("message", "Task completed")),
                "success": action.get("success", True),
            }
        return {"_metadata": "do", **action}
    if isinstance(action, str):
        copied = {k: v for k, v in payload.items() if k not in {"thinking", "thought"}}
        copied["_metadata"] = "do"
        return copied
    return None


def _extract_first_call(text: str) -> str:
    """Extract the first balanced ``do(...)`` or ``finish(...)`` call."""
    matches = list(re.finditer(r"(?<![\w])(?:do|finish)\s*\(", text))
    if not matches:
        raise ActionParseError(f"No do(...) or finish(...) call found: {text[:200]}")

    start = matches[0].start()
    depth = 0
    quote: str | None = None
    escaped = False

    for pos in range(start, len(text)):
        ch = text[pos]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {'"', "'"}:
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start : pos + 1].strip()
    return text[start:].strip()


def _parse_do_call(call_text: str) -> dict[str, Any]:
    try:
        call = _parse_call_ast(call_text)
    except ActionParseError:
        fallback = _parse_type_call_fallback(call_text)
        if fallback is not None:
            return fallback
        raise

    if not isinstance(call.func, ast.Name) or call.func.id != "do":
        raise ActionParseError("Expected do(...) call")
    if call.args:
        raise ActionParseError("Positional arguments are not allowed in do(...)")

    action: dict[str, Any] = {"_metadata": "do"}
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ActionParseError("**kwargs is not allowed in action calls")
        try:
            action[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as exc:
            raise ActionParseError(
                f"Action keyword {keyword.arg!r} must be a literal value"
            ) from exc
    return action


def _parse_finish_call(call_text: str) -> dict[str, Any]:
    try:
        call = _parse_call_ast(call_text)
    except ActionParseError:
        fallback = _parse_finish_call_fallback(call_text)
        if fallback is not None:
            return fallback
        raise

    if not isinstance(call.func, ast.Name) or call.func.id != "finish":
        raise ActionParseError("Expected finish(...) call")
    if call.args:
        raise ActionParseError("Positional arguments are not allowed in finish(...)")

    parsed: dict[str, Any] = {
        "_metadata": "finish",
        "message": "Task completed",
        "success": True,
    }
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ActionParseError("**kwargs is not allowed in finish calls")
        try:
            parsed[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as exc:
            raise ActionParseError(
                f"Finish keyword {keyword.arg!r} must be a literal value"
            ) from exc
    return parsed


def _parse_call_ast(call_text: str) -> ast.Call:
    try:
        tree = ast.parse(call_text, mode="eval")
    except SyntaxError as exc:
        raise ActionParseError(f"Invalid Python-style action syntax: {exc}") from exc
    if not isinstance(tree.body, ast.Call):
        raise ActionParseError("Action must be a function call")
    return tree.body


def _parse_type_call_fallback(call_text: str) -> dict[str, Any] | None:
    action_match = re.search(r"action\s*=\s*(['\"])(.*?)\1", call_text, flags=re.DOTALL)
    text_match = re.search(r"text\s*=\s*(['\"])(.*?)\1\s*\)?\s*$", call_text, flags=re.DOTALL)
    if not action_match or not text_match:
        return None
    if _canonical_action_name(action_match.group(2)) != "Type":
        return None
    return {"_metadata": "do", "action": "Type", "text": text_match.group(2)}


def _parse_finish_call_fallback(call_text: str) -> dict[str, Any] | None:
    if not re.match(r"^finish\s*\(", call_text):
        return None
    inner = call_text[call_text.find("(") + 1 :].strip()
    if inner.endswith(")"):
        inner = inner[:-1].strip()
    message = _extract_string_keyword_loose(inner, "message")
    if message is None:
        return None
    success_match = re.search(r"success\s*=\s*(True|False)", inner)
    success = success_match is None or success_match.group(1) == "True"
    return {"_metadata": "finish", "message": message, "success": success}


def _extract_string_keyword_loose(text: str, keyword: str) -> str | None:
    patterns = [
        rf"{keyword}\s*=\s*(['\"])(.*?)\1(?=\s*(?:,|$))",
        rf"{keyword}\s*=\s*(['\"])(.*)\1\s*$",
        rf"{keyword}\s*=\s*(['\"])(.*)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            return match.group(2).strip()
    return None


def _canonical_action_name(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip().replace("-", "_")).lower()
    return _ACTION_ALIASES.get(normalized)


def _validate_relative_coordinate(value: Any, field_name: str) -> list[float | int]:
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


class ActionHandler:
    """Execute validated Android actions with confirmation and duration limits."""

    def __init__(
        self,
        device: AndroidDevice,
        confirmation_callback: ConfirmationCallback | None = None,
        takeover_callback: TakeoverCallback | None = None,
        note_callback: NoteCallback | None = None,
        api_callback: APICallback | None = None,
        *,
        max_wait_seconds: float = 15.0,
        max_gesture_duration_ms: int = 10_000,
    ):
        self.device = device
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover
        self.note_callback = note_callback
        self.api_callback = api_callback
        self.max_wait_seconds = max(0.0, float(max_wait_seconds))
        self.max_gesture_duration_ms = max(1, int(max_gesture_duration_ms))
        self.task = ""
        self.notes: list[str] = []

    def set_task(self, task: str) -> None:
        self.task = str(task or "")

    def execute(
        self, action: dict[str, Any], screen_width: int, screen_height: int
    ) -> ActionResult:
        try:
            action = validate_action(action)
        except ActionParseError as exc:
            return ActionResult(
                False,
                False,
                str(exc),
                error_code="invalid_action",
            )

        action_type = action.get("_metadata")
        if action_type == "finish":
            return ActionResult(
                bool(action.get("success", True)),
                True,
                str(action.get("message", "Task completed")),
            )

        action_name = str(action["action"])
        handlers: dict[str, Callable[[dict[str, Any], int, int], ActionResult]] = {
            "Launch": self._handle_launch,
            "Tap": self._handle_tap,
            "Type": self._handle_type,
            "Swipe": self._handle_swipe,
            "Back": self._handle_back,
            "Home": self._handle_home,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Interact": self._handle_interact,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
        }

        confirmation_message = self._confirmation_message(action)
        if confirmation_message:
            if not self.confirmation_callback(confirmation_message):
                return ActionResult(
                    False,
                    True,
                    "User cancelled sensitive operation",
                    requires_confirmation=True,
                    error_code="user_cancelled",
                )

        try:
            return handlers[action_name](action, screen_width, screen_height)
        except Exception as exc:  # Convert device errors into structured runtime feedback.
            return ActionResult(
                False,
                False,
                f"{action_name} failed: {exc}",
                error_code="action_execution_failed",
                metadata={"exception_type": type(exc).__name__},
            )

    @staticmethod
    def _relative_to_absolute(
        element: list[int | float], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError(
                f"Invalid display size: {screen_width}x{screen_height}"
            )
        x = ActionHandler._scale_relative_coordinate(element[0], screen_width)
        y = ActionHandler._scale_relative_coordinate(element[1], screen_height)
        return x, y

    @staticmethod
    def _scale_relative_coordinate(value: int | float, size: int) -> int:
        if size <= 1:
            return 0
        scaled = round(float(value) / 999 * (size - 1))
        return max(0, min(size - 1, int(scaled)))

    def _handle_launch(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        app_name = str(action["app"])
        resolved_launch = getattr(self.device, "launch_app_resolved", None)
        if callable(resolved_launch):
            result = resolved_launch(app_name)
            payload = result.to_dict()
            metadata = {
                "app": app_name,
                "app_launch": payload,
                "package_name": result.app.package_name if result.app else None,
                "activity_name": result.app.activity_name if result.app else None,
                "launch_status": result.status.value,
                "visual_completion_required": not result.fully_launched and result.success,
            }
            if result.success:
                return ActionResult(
                    True,
                    False,
                    message=result.message,
                    metadata=metadata,
                )
            return ActionResult(
                False,
                False,
                message=result.message,
                error_code=(
                    result.failure_reason.value
                    if result.failure_reason is not None
                    else "app_launch_failed"
                ),
                metadata=metadata,
            )

        # Compatibility path for test devices and third-party device adapters.
        if self.device.launch_app(app_name):
            return ActionResult(True, False, metadata={"app": app_name})
        return ActionResult(
            False,
            False,
            f"App alias or package not found: {app_name}",
            error_code="app_not_found",
        )

    def _handle_tap(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        x, y = self._relative_to_absolute(action["element"], width, height)
        self.device.tap(x, y)
        return ActionResult(True, False, metadata={"x": x, "y": y})

    def _handle_double_tap(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        x, y = self._relative_to_absolute(action["element"], width, height)
        self.device.double_tap(x, y)
        return ActionResult(True, False, metadata={"x": x, "y": y})

    def _handle_long_press(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        duration_ms = min(
            int(action.get("duration_ms", 800)), self.max_gesture_duration_ms
        )
        x, y = self._relative_to_absolute(action["element"], width, height)
        self.device.long_press(x, y, duration_ms=duration_ms)
        return ActionResult(
            True,
            False,
            metadata={"x": x, "y": y, "duration_ms": duration_ms},
        )

    def _handle_swipe(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        start_x, start_y = self._relative_to_absolute(action["start"], width, height)
        end_x, end_y = self._relative_to_absolute(action["end"], width, height)
        duration_ms = action.get("duration_ms")
        if duration_ms is not None:
            duration_ms = min(int(duration_ms), self.max_gesture_duration_ms)
        self.device.swipe(
            start_x, start_y, end_x, end_y, duration_ms=duration_ms
        )
        return ActionResult(
            True,
            False,
            metadata={
                "start": [start_x, start_y],
                "end": [end_x, end_y],
                "duration_ms": duration_ms,
            },
        )

    def _handle_type(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        if action.get("clear") is True:
            self.device.clear_text()
        self.device.type_text(str(action.get("text", "")))
        return ActionResult(True, False)

    def _handle_back(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        self.device.back()
        return ActionResult(True, False)

    def _handle_home(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        self.device.home()
        return ActionResult(True, False)

    def _handle_wait(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        requested = _parse_duration_seconds(action.get("duration", "1 second"))
        duration = min(requested, self.max_wait_seconds)
        time.sleep(duration)
        message = None
        if duration < requested:
            message = (
                f"Wait duration was capped from {requested:g}s to {duration:g}s"
            )
        return ActionResult(
            True,
            False,
            message=message,
            metadata={"requested_seconds": requested, "waited_seconds": duration},
        )

    def _handle_takeover(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        message = str(action.get("message", "Manual operation required"))
        self.takeover_callback(message)
        return ActionResult(True, False, message="Manual operation completed")

    def _handle_interact(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        message = str(
            action.get("message", "User choice or manual interaction is required")
        )
        self.takeover_callback(message)
        return ActionResult(True, False, message="User interaction completed")

    def _handle_note(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        note = str(action.get("message", action.get("text", ""))).strip()
        if not note:
            return ActionResult(
                False,
                False,
                "Note action requires message or text",
                error_code="empty_note",
            )
        self.notes.append(note)
        if self.note_callback is not None:
            self.note_callback(note)
        return ActionResult(True, False, message="Note recorded")

    def _handle_call_api(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        instruction = str(action.get("instruction", "")).strip()
        if not instruction:
            return ActionResult(
                False,
                False,
                "Call_API requires instruction",
                error_code="empty_api_instruction",
            )
        if self.api_callback is None:
            return ActionResult(
                False,
                False,
                "Call_API is not configured in this runtime",
                error_code="api_callback_not_configured",
            )
        output = self.api_callback(instruction)
        return ActionResult(True, False, message=output or "API call completed")

    @staticmethod
    def _confirmation_message(action: dict[str, Any]) -> str | None:
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

        sensitive_keywords = (
            "支付", "付款", "转账", "提现", "购买", "下单", "提交订单",
            "确认订单", "确认支付", "发送", "发布", "删除", "清空", "注销",
            "授权", "允许", "同意", "退款", "挂号", "预约", "拨打", "呼叫",
            "pay", "purchase", "place order", "send", "post", "publish",
            "delete", "clear", "authorize", "allow", "confirm order",
        )
        text_fields = (
            "label", "description", "instruction", "message", "target"
        )
        haystack = " ".join(str(action.get(field, "")) for field in text_fields).strip()
        if haystack and any(keyword in haystack.casefold() for keyword in sensitive_keywords):
            return f"Sensitive operation detected: {haystack}"
        return None

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.strip().upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        input(f"{message}\nPress Enter after completing the manual operation...")


def _parse_duration_seconds(duration: str | int | float) -> float:
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
