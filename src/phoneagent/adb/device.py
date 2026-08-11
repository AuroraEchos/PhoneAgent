"""Device control utilities for Android automation."""

from __future__ import annotations

import base64
import re
import time

from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.config.apps import APP_PACKAGES, get_canonical_app_name, get_package_name
from phoneagent.config.timing import TIMING_CONFIG


ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

DEFAULT_ACTION_TIMEOUT = 5
DEFAULT_QUERY_TIMEOUT = 10
DEFAULT_LAUNCH_TIMEOUT = 15

_SYSTEM_PANEL_WINDOW_MARKERS = (
    "notificationshade",
    "quicksettings",
    "quick settings",
    "controlcenter",
    "control center",
    "supercard",
)


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


def _extract_system_panel_state(output: str) -> tuple[bool | None, str | None]:
    """Extract whether a notification/quick-settings overlay is visible.

    WindowManager keeps many panel windows registered even while they are
    collapsed, so merely finding ``NotificationShade`` is not sufficient.  A
    focused panel is definitive; otherwise inspect the matching window block
    for a visible or shown surface.  Unknown OEM layouts return ``None`` rather
    than pretending that the panel is closed.
    """
    if not output.strip():
        return None, None

    for line in output.splitlines():
        folded = line.casefold()
        if "mcurrentfocus=" not in folded:
            continue
        marker = next(
            (value for value in _SYSTEM_PANEL_WINDOW_MARKERS if value in folded),
            None,
        )
        if marker is not None and "null" not in folded:
            return True, marker

    block_start = re.compile(r"(?m)^\s*Window #\d+ Window\{")
    starts = list(block_start.finditer(output))
    matching_names: list[str] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(output)
        block = output[match.start() : end]
        folded = block.casefold()
        marker = next(
            (value for value in _SYSTEM_PANEL_WINDOW_MARKERS if value in folded),
            None,
        )
        if marker is None:
            continue
        matching_names.append(marker)
        if "isvisible=true" in folded or "surface: shown=true" in folded:
            return True, marker

    if matching_names:
        return False, matching_names[0]
    return None, None


def _package_to_app_name(package: str) -> str | None:
    """Map a package name back to its canonical configured app name."""
    return get_canonical_app_name(package)


def get_window_state(
    device_id: str | None = None,
) -> tuple[str, bool | None, str | None]:
    """Return the focused app and non-sensitive system-panel visibility state."""
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
    panel_visible, panel_name = _extract_system_panel_state(output)
    if not package:
        return "Unknown", panel_visible, panel_name

    app_name = _package_to_app_name(package)
    if app_name:
        return app_name, panel_visible, panel_name

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
        return "System Home", panel_visible, panel_name

    return f"Unknown ({package})", panel_visible, panel_name


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
    current_app, _panel_visible, _panel_name = get_window_state(device_id)
    return current_app


def statusbar_command(command: str, device_id: str | None = None):
    """Run one allowlisted ``cmd statusbar`` panel command without retries."""
    allowed = {"expand-notifications", "expand-settings", "collapse"}
    if command not in allowed:
        raise ValueError(f"Unsupported statusbar command: {command!r}")
    return run_adb(
        ["shell", "cmd", "statusbar", command],
        device_id=device_id,
        timeout=DEFAULT_ACTION_TIMEOUT,
        check=False,
    )


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


def is_package_installed(
    package_name: str,
    device_id: str | None = None,
) -> bool:
    """Return whether ``package_name`` is installed on the selected device."""
    package = str(package_name or "").strip()
    if not package:
        return False
    result = run_adb(
        ["shell", "pm", "path", package],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        check=False,
        retries=1,
    )
    return result.returncode == 0 and any(
        line.strip().startswith("package:") for line in (result.stdout or "").splitlines()
    )


def list_installed_packages(device_id: str | None = None) -> set[str]:
    """Return all package names reported by Android PackageManager."""
    result = run_adb(
        ["shell", "pm", "list", "packages"],
        device_id=device_id,
        timeout=DEFAULT_QUERY_TIMEOUT,
        retries=1,
    )
    packages: set[str] = set()
    for line in (result.stdout or "").splitlines():
        value = line.strip()
        if value.startswith("package:"):
            package = value[len("package:") :].strip()
            if package:
                packages.add(package)
    return packages


def launch_package(
    package_name: str,
    device_id: str | None = None,
    delay: float | None = None,
    *,
    timeout: float = DEFAULT_LAUNCH_TIMEOUT,
) -> None:
    """Launch an installed package through its launcher intent."""
    package = str(package_name or "").strip()
    if not package:
        raise ValueError("package_name cannot be empty")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

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
        timeout=timeout,
        check=False,
    )
    output_lower = _combined_output(result).lower()
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


def launch_app(
    app_name: str,
    device_id: str | None = None,
    delay: float | None = None,
) -> bool:
    """Resolve a configured alias or package and launch it through ADB."""
    package = get_package_name(app_name)
    if package is None:
        return False
    launch_package(package, device_id=device_id, delay=delay)
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
