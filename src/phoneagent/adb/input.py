"""Compatibility wrappers for Android text input.

The canonical implementation lives in :mod:`src.adb.device`.  This module is
kept so older imports continue to work while the runtime uses one input path.
"""

from __future__ import annotations

from phoneagent.adb.device import (
    ADB_KEYBOARD_IME,
    clear_text,
    detect_and_set_adb_keyboard,
    get_current_input_method,
    restore_keyboard,
    type_text,
)

__all__ = [
    "ADB_KEYBOARD_IME",
    "get_current_input_method",
    "detect_and_set_adb_keyboard",
    "restore_keyboard",
    "type_text",
    "clear_text",
]
