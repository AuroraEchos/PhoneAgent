"""Device control utilities for Android automation."""

from __future__ import annotations

import base64
import re
import time

from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.config.apps import APP_PACKAGES, get_package_name
from phoneagent.config.timing import TIMING_CONFIG


ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

DEFAULT_ACTION_TIMEOUT = 5
DEFAULT_QUERY_TIMEOUT = 10
DEFAULT_LAUNCH_TIMEOUT = 15


def _validate_coordinate(x: int, y: int) -> None:
    """Validate screen coordinates."""
    if not isinstance(x, int) or not isinstance(y, int):
        raise TypeError(f"Coordinates must be integers, got x={type(x)}, y={type(y)}")

    if x < 0 or y < 0:
        raise ValueError(f"Coordinates must be non-negative, got x={x}, y={y}")


def _validate_duration_ms(duration_ms: int, *, name: str = "duration_ms") -> None:
    """Validate an ADB input duration."""
    if not isinstance(duration_ms, int):
        raise TypeError(f"{name} must be an integer, got {type(duration_ms)}")

    if duration_ms <= 0:
        raise ValueError(f"{name} must be positive, got {duration_ms}")


def _sleep_after_action(delay: float | None) -> None:
    """Sleep after an action when delay is positive."""
    if delay is not None and delay > 0:
        time.sleep(delay)


def _combined_output(result) -> str:
    """Combine stdout and stderr for command result inspection."""
    return f"{result.stdout or ''}\n{result.stderr or ''}".strip()


def _extract_focused_package(output: str) -> str | None:
    """
    Extract the currently focused package name from dumpsys window output.

    Different Android versions expose focus information in slightly different forms,
    for example:

        mCurrentFocus=Window{... u0 com.android.settings/com.android.settings.Settings}
        mFocusedApp=ActivityRecord{... com.android.settings/.Settings}
        topResumedActivity=ActivityRecord{... com.android.chrome/...}
    """
    focus_keywords = (
        "mCurrentFocus",
        "mFocusedApp",
        "topResumedActivity",
        "mTopActivity",
    )

    package_pattern = re.compile(r"([a-zA-Z][\w]*(?:\.[\w]+)+)/")

    for line in output.splitlines():
        if not any(keyword in line for keyword in focus_keywords):
            continue

        match = package_pattern.search(line)
        if match:
            return match.group(1)

    return None


def _package_to_app_name(package: str) -> str | None:
    """Map package name back to configured app alias."""
    for app_name, app_package in APP_PACKAGES.items():
        if app_package == package:
            return app_name
    return None


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        Recognized app alias if known.
        "System Home" for common launcher/system home packages.
        "Unknown (<package>)" for unknown third-party/system apps.
        "Unknown" if the focused package cannot be parsed.
    """
    result = run_adb(
        ["shell", "dumpsys", "window"],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        retries=1,
    )

    output = result.stdout
    if not output:
        raise ValueError("No output from dumpsys window")

    package = _extract_focused_package(output)
    if not package:
        return "Unknown"

    app_name = _package_to_app_name(package)
    if app_name:
        return app_name

    home_packages = {
        "com.android.launcher",
        "com.android.launcher2",
        "com.android.launcher3",
        "com.google.android.apps.nexuslauncher",
        "com.miui.home",
        "com.huawei.android.launcher",
        "com.oppo.launcher",
        "com.vivo.launcher",
        "com.sec.android.app.launcher",
    }

    if package in home_packages or "launcher" in package.lower():
        return "System Home"

    return f"Unknown ({package})"


def get_screen_size(device_id: str | None = None) -> tuple[int, int]:
    """
    Get physical screen size.

    Args:
        device_id: Optional ADB device ID.

    Returns:
        Tuple of (width, height).

    Raises:
        ValueError if screen size cannot be parsed.
    """
    result = run_adb(
        ["shell", "wm", "size"],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        retries=1,
    )

    output = result.stdout.strip()
    match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    if not match:
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)

    if not match:
        raise ValueError(f"Failed to parse screen size from output: {output}")

    return int(match.group(1)), int(match.group(2))


def tap(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    _validate_coordinate(x, y)

    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    run_adb(
        ["shell", "input", "tap", x, y],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def double_tap(
    x: int,
    y: int,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    _validate_coordinate(x, y)

    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    run_adb(
        ["shell", "input", "tap", x, y],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    run_adb(
        ["shell", "input", "tap", x, y],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 800,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    _validate_coordinate(x, y)
    _validate_duration_ms(duration_ms)

    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    run_adb(
        ["shell", "input", "swipe", x, y, x, y, duration_ms],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds. Auto-calculated if None.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    _validate_coordinate(start_x, start_y)
    _validate_coordinate(end_x, end_y)

    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    if duration_ms is None:
        distance = ((start_x - end_x) ** 2 + (start_y - end_y) ** 2) ** 0.5
        duration_ms = int(distance * 0.45)
        duration_ms = max(250, min(duration_ms, 1000))
    else:
        _validate_duration_ms(duration_ms)

    run_adb(
        [
            "shell",
            "input",
            "swipe",
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms,
        ],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    run_adb(
        ["shell", "input", "keyevent", "KEYCODE_BACK"],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    run_adb(
        ["shell", "input", "keyevent", "KEYCODE_HOME"],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def launch_app(
    app_name: str,
    device_id: str | None = None,
    delay: float | None = None,
) -> bool:
    """
    Launch an app by configured app alias.

    Args:
        app_name: The app name or alias. Must exist in APP_PACKAGES.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if app was launched.
        False if app_name is not configured.

    Raises:
        ADBCommandError if adb reports a launch failure for a configured package.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    package = get_package_name(app_name)
    if package is None:
        return False

    result = run_adb(
        [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        device_id=device_id,
        timeout=DEFAULT_LAUNCH_TIMEOUT,
        check=False,
    )

    output = _combined_output(result)
    output_lower = output.lower()

    failed_markers = (
        "error:",
        "no activities found",
        "monkey aborted",
        "permission denied",
        "unable to resolve",
    )

    if result.returncode != 0 or any(marker in output_lower for marker in failed_markers):
        raise ADBCommandError(
            result.args,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            reason=f"failed to launch package {package}",
        )

    _sleep_after_action(delay)
    return True


def force_stop_app(
    app_name: str,
    device_id: str | None = None,
    delay: float | None = None,
) -> bool:
    """
    Force stop an app by configured app alias.

    Args:
        app_name: The app name or alias. Must exist in APP_PACKAGES.
        device_id: Optional ADB device ID.
        delay: Delay after force stopping.

    Returns:
        True if force-stop command was issued.
        False if app_name is not configured.
    """
    if app_name not in APP_PACKAGES:
        return False

    if delay is None:
        delay = 0.5

    package = APP_PACKAGES[app_name]

    run_adb(
        ["shell", "am", "force-stop", package],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)
    return True


def is_adb_keyboard_installed(device_id: str | None = None) -> bool:
    """
    Check whether ADB Keyboard is installed.

    Args:
        device_id: Optional ADB device ID.

    Returns:
        True if ADB Keyboard IME exists.
    """
    result = run_adb(
        ["shell", "ime", "list", "-s"],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        check=False,
    )

    return result.returncode == 0 and ADB_KEYBOARD_IME in (result.stdout or "")


def get_current_input_method(device_id: str | None = None) -> str:
    """
    Return the currently active Android input method identifier.

    Args:
        device_id: Optional ADB device ID.
    """
    result = run_adb(
        ["shell", "settings", "get", "secure", "default_input_method"],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ADBCommandError(
            result.args,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            reason="failed to query current input method",
        )
    return (result.stdout or "").strip()


def is_adb_keyboard_active(device_id: str | None = None) -> bool:
    """
    Check whether ADB Keyboard is the current input method.

    Args:
        device_id: Optional ADB device ID.

    Returns:
        True if ADB Keyboard is active.
    """
    return get_current_input_method(device_id) == ADB_KEYBOARD_IME


def set_adb_keyboard(device_id: str | None = None, delay: float | None = None) -> bool:
    """
    Switch current input method to ADB Keyboard.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay after switching input method.

    Returns:
        True if ADB Keyboard is active after the command.
    """
    if delay is None:
        delay = TIMING_CONFIG.action.keyboard_switch_delay

    if is_adb_keyboard_active(device_id):
        return True

    if not is_adb_keyboard_installed(device_id):
        return False

    result = run_adb(
        ["shell", "ime", "set", ADB_KEYBOARD_IME],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
        check=False,
    )

    if result.returncode != 0:
        return False

    _sleep_after_action(delay)
    return is_adb_keyboard_active(device_id)


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Switch to ADB Keyboard when needed and return the previous input method.

    This is useful for callers that want to restore the user's original keyboard
    after a controlled operation.  The agent runtime usually keeps ADB Keyboard
    active for reliability across multiple Type actions.
    """
    original_ime = get_current_input_method(device_id)
    if original_ime != ADB_KEYBOARD_IME and not set_adb_keyboard(device_id):
        raise RuntimeError(
            "ADB Keyboard is not installed or cannot be activated. "
            "Install it from: https://github.com/senzhk/ADBKeyBoard"
        )
    return original_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore a previously active input method.

    Empty or already-active values are ignored to avoid unnecessary adb calls.
    """
    ime = (ime or "").strip()
    if not ime or ime == get_current_input_method(device_id):
        return
    run_adb(
        ["shell", "ime", "set", ime],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(TIMING_CONFIG.action.keyboard_restore_delay)


def type_text(
    text: str,
    device_id: str | None = None,
    delay: float | None = None,
    *,
    ensure_adb_keyboard: bool = True,
) -> None:
    """
    Type text into the currently focused input field.

    This uses ADB Keyboard's Base64 broadcast protocol.  It is safer than
    ``adb shell input text`` and avoids shell escaping problems for Chinese,
    spaces, quotes and other special characters.
    """
    if delay is None:
        delay = TIMING_CONFIG.action.text_input_delay

    if ensure_adb_keyboard and not set_adb_keyboard(device_id):
        raise RuntimeError(
            "ADB Keyboard is not installed or cannot be activated. "
            "Install it from: https://github.com/senzhk/ADBKeyBoard"
        )

    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    run_adb(
        [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)


def clear_text(
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Clear text in the currently focused input field using ADB Keyboard.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay after clearing text.
    """
    if delay is None:
        delay = TIMING_CONFIG.action.text_clear_delay

    if not set_adb_keyboard(device_id):
        raise RuntimeError(
            "ADB Keyboard is not installed or cannot be activated. "
            "Install it from: https://github.com/senzhk/ADBKeyBoard"
        )

    run_adb(
        ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
    )
    _sleep_after_action(delay)
