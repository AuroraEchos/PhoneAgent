from __future__ import annotations

import threading
import time

import pytest

from phoneagent.actions import ActionHandler, ActionParseError, do, parse_action
from phoneagent.adb.device import _extract_system_panel_state
from phoneagent.devices import SystemPanelCommandResult


def test_parse_tap_action() -> None:
    action = parse_action('do(action="Tap", element=[500, 250])')
    assert action == {"_metadata": "do", "action": "Tap", "element": [500, 250]}


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ('do(action="OpenNotifications")', "OpenNotifications"),
        ('do(action="open_quick_settings")', "OpenQuickSettings"),
        ('do(action="close-system-panel")', "CloseSystemPanel"),
    ],
)
def test_parse_system_panel_actions(text: str, canonical: str) -> None:
    assert parse_action(text)["action"] == canonical


def test_parser_rejects_json_action() -> None:
    with pytest.raises(ActionParseError):
        parse_action('{"type":"finish","message":"done","success":true}')


def test_parser_rejects_executable_python() -> None:
    with pytest.raises(ActionParseError):
        parse_action('do(action="Tap", element=__import__("os").system("id"))')


def test_coordinate_scaling_is_bounded() -> None:
    assert ActionHandler._relative_to_absolute([0, 0], 1080, 2400) == (0, 0)
    assert ActionHandler._relative_to_absolute([999, 999], 1080, 2400) == (1079, 2399)
    assert ActionHandler._relative_to_absolute([500, 500], 1080, 2400) == (540, 1201)


def test_wait_action_is_cancelled_without_waiting_for_full_duration() -> None:
    cancel_event = threading.Event()
    handler = ActionHandler(object(), cancel_event=cancel_event)  # type: ignore[arg-type]
    results = []
    started = time.monotonic()
    thread = threading.Thread(
        target=lambda: results.append(
            handler.execute(do(action="Wait", duration="10 seconds"), 1, 1)
        )
    )
    thread.start()
    time.sleep(0.05)
    cancel_event.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert time.monotonic() - started < 1
    assert results[0].error_code == "user_cancelled"


def test_system_panel_action_uses_semantic_device_command() -> None:
    class Device:
        def open_notifications(self) -> SystemPanelCommandResult:
            return SystemPanelCommandResult(
                target="notifications",
                command="expand-notifications",
                success=True,
                returncode=0,
                message="requested",
            )

    result = ActionHandler(Device()).execute(  # type: ignore[arg-type]
        do(action="OpenNotifications"), 1080, 2400
    )

    assert result.success is True
    assert result.metadata["system_panel"]["transport"] == "cmd_statusbar"
    assert result.metadata["system_panel"]["command"] == "expand-notifications"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "mCurrentFocus=Window{abc u0 NotificationShade type=2040 }",
            (True, "notificationshade"),
        ),
        (
            "mCurrentFocus=Window{abc u0 com.example/.MainActivity type=1 }\n"
            "Window #6 Window{def u0 NotificationShade type=2040 }:\n"
            "  mHasSurface=false\n  isVisible=false",
            (False, "notificationshade"),
        ),
        (
            "mCurrentFocus=Window{abc u0 com.example/.MainActivity type=1 }",
            (None, None),
        ),
    ],
)
def test_system_panel_visibility_uses_window_state(output, expected) -> None:
    assert _extract_system_panel_state(output) == expected
