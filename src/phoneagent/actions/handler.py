"""Validated action execution for Android PhoneAgent."""

from __future__ import annotations

from threading import Event
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from phoneagent.actions.protocol import (
    ActionParseError,
    do,
    finish,
    parse_action,
    validate_action,
)
from phoneagent.actions.policy import confirmation_message, parse_duration_seconds
from phoneagent.devices import AndroidDevice


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


class ActionHandler:
    """Execute validated Android actions with confirmation and duration limits."""

    def __init__(
        self,
        device: AndroidDevice,
        confirmation_callback: ConfirmationCallback | None = None,
        takeover_callback: TakeoverCallback | None = None,
        note_callback: NoteCallback | None = None,
        api_callback: APICallback | None = None,
        cancel_event: Event | None = None,
        *,
        max_wait_seconds: float = 15.0,
        max_gesture_duration_ms: int = 10_000,
    ):
        self.device = device
        self.confirmation_callback = confirmation_callback or self._default_confirmation
        self.takeover_callback = takeover_callback or self._default_takeover
        self.note_callback = note_callback
        self.api_callback = api_callback
        self.cancel_event = cancel_event
        self.max_wait_seconds = max(0.0, float(max_wait_seconds))
        self.max_gesture_duration_ms = max(1, int(max_gesture_duration_ms))
        self.task = ""
        self.notes: list[str] = []
        self._original_input_method: str | None = None

    def set_task(self, task: str) -> None:
        self.task = str(task or "")

    def restore_input_method(self) -> str | None:
        """Restore the keyboard captured by the first Type action in this task."""
        original = self._original_input_method
        self._original_input_method = None
        restore = getattr(self.device, "restore_keyboard", None)
        if original is None or not callable(restore):
            return None
        try:
            restore(original)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return None

    def request_confirmation(self, action: dict[str, Any]) -> ActionResult | None:
        """Ask for confirmation without dispatching the validated action."""
        try:
            action = validate_action(action)
        except ActionParseError as exc:
            return ActionResult(False, False, str(exc), error_code="invalid_action")
        message = self._confirmation_message(action)
        if message and not self.confirmation_callback(message):
            return ActionResult(
                False,
                True,
                "User cancelled sensitive operation",
                requires_confirmation=True,
                error_code="user_cancelled",
            )
        return None

    def execute(
        self,
        action: dict[str, Any],
        screen_width: int,
        screen_height: int,
        *,
        confirmation_checked: bool = False,
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
            "OpenNotifications": self._handle_open_notifications,
            "OpenQuickSettings": self._handle_open_quick_settings,
            "CloseSystemPanel": self._handle_close_system_panel,
            "Double Tap": self._handle_double_tap,
            "Long Press": self._handle_long_press,
            "Wait": self._handle_wait,
            "Take_over": self._handle_takeover,
            "Interact": self._handle_interact,
            "Note": self._handle_note,
            "Call_API": self._handle_call_api,
        }

        if not confirmation_checked:
            confirmation_result = self.request_confirmation(action)
            if confirmation_result is not None:
                return confirmation_result

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

    def execute_system_panel_fallback(
        self,
        action: dict[str, Any],
        screen_width: int,
        screen_height: int,
    ) -> ActionResult:
        """Execute the hidden edge-gesture fallback for an open-panel action."""
        try:
            action = validate_action(action)
            action_name = str(action.get("action", ""))
            if action_name not in {"OpenNotifications", "OpenQuickSettings"}:
                raise ActionParseError(
                    f"System-panel fallback is unavailable for {action_name!r}"
                )
            metadata = self.device.open_system_panel_gesture(
                action_name,
                screen_width,
                screen_height,
            )
            return ActionResult(
                True,
                False,
                message=f"Executed {action_name} edge-gesture fallback",
                metadata={"system_panel": metadata, "internal_fallback": True},
            )
        except Exception as exc:
            return ActionResult(
                False,
                False,
                message=f"System-panel gesture fallback failed: {exc}",
                error_code="system_panel_fallback_failed",
                metadata={"exception_type": type(exc).__name__, "internal_fallback": True},
            )

    @staticmethod
    def _relative_to_absolute(
        element: list[int | float], screen_width: int, screen_height: int
    ) -> tuple[int, int]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError(f"Invalid display size: {screen_width}x{screen_height}")
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
        del width, height
        app_name = str(action["app"])
        resolved_launch = getattr(self.device, "launch_app_resolved", None)
        if callable(resolved_launch):
            result = resolved_launch(app_name)
            metadata = {
                "app": app_name,
                "app_launch": result.to_dict(),
                "package_name": result.package_name,
                "display_name": result.display_name,
            }
            return ActionResult(
                success=result.success,
                should_finish=False,
                message=result.message,
                error_code=result.error_code,
                metadata=metadata,
            )

        # Compatibility path for simple third-party device adapters.
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
        duration_ms = min(int(action.get("duration_ms", 800)), self.max_gesture_duration_ms)
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
        self.device.swipe(start_x, start_y, end_x, end_y, duration_ms=duration_ms)
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
        prepare_keyboard = getattr(self.device, "detect_and_set_adb_keyboard", None)
        if self._original_input_method is None and callable(prepare_keyboard):
            self._original_input_method = str(prepare_keyboard() or "")
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

    def _handle_open_notifications(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        del action, width, height
        return self._system_panel_command_result(self.device.open_notifications())

    def _handle_open_quick_settings(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        del action, width, height
        return self._system_panel_command_result(self.device.open_quick_settings())

    def _handle_close_system_panel(
        self, action: dict[str, Any], width: int, height: int
    ) -> ActionResult:
        del action, width, height
        return self._system_panel_command_result(self.device.close_system_panel())

    @staticmethod
    def _system_panel_command_result(result: Any) -> ActionResult:
        metadata = result.to_dict()
        return ActionResult(
            bool(result.success),
            False,
            message=str(result.message),
            error_code=None if result.success else "system_panel_command_failed",
            metadata={"system_panel": metadata},
        )

    def _handle_wait(self, action: dict[str, Any], width: int, height: int) -> ActionResult:
        requested = parse_duration_seconds(action.get("duration", "1 second"))
        duration = min(requested, self.max_wait_seconds)
        if self.cancel_event is not None and self.cancel_event.wait(duration):
            return ActionResult(
                False,
                True,
                message="Task cancelled during wait",
                error_code="user_cancelled",
                metadata={"requested_seconds": requested, "waited_seconds": None},
            )
        if self.cancel_event is None:
            time.sleep(duration)
        message = None
        if duration < requested:
            message = f"Wait duration was capped from {requested:g}s to {duration:g}s"
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
        message = str(action.get("message", "User choice or manual interaction is required"))
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
        return confirmation_message(action)

    @staticmethod
    def _default_confirmation(message: str) -> bool:
        response = input(f"Sensitive operation: {message}\nConfirm? (Y/N): ")
        return response.strip().upper() == "Y"

    @staticmethod
    def _default_takeover(message: str) -> None:
        input(f"{message}\nPress Enter after completing the manual operation...")
