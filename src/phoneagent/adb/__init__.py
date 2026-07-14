"""ADB utilities for Android device interaction."""

from phoneagent.adb.command import ADBCommandError, build_adb_command, run_adb
from phoneagent.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phoneagent.adb.device import (
    ADB_KEYBOARD_IME,
    back,
    clear_text,
    detect_and_set_adb_keyboard,
    double_tap,
    get_current_app,
    get_current_input_method,
    home,
    is_adb_keyboard_active,
    is_adb_keyboard_installed,
    launch_app,
    long_press,
    restore_keyboard,
    set_adb_keyboard,
    swipe,
    tap,
    type_text,
)
from phoneagent.adb.screenshot import Screenshot, ScreenshotCaptureError, get_screenshot

__all__ = [
    # Screenshot
    "Screenshot",
    "ScreenshotCaptureError",
    "get_screenshot",
    "ADBCommandError",
    "build_adb_command",
    "run_adb",
    # Input
    "ADB_KEYBOARD_IME",
    "type_text",
    "clear_text",
    "detect_and_set_adb_keyboard",
    "get_current_input_method",
    "is_adb_keyboard_active",
    "is_adb_keyboard_installed",
    "restore_keyboard",
    "set_adb_keyboard",
    # Device control
    "get_current_app",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
]
