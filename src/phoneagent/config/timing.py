"""Validated timing configuration for PhoneAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_non_negative_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


@dataclass(slots=True)
class ActionTimingConfig:
    keyboard_switch_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_KEYBOARD_SWITCH_DELAY", 0.5
        )
    )
    text_clear_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_TEXT_CLEAR_DELAY", 0.35
        )
    )
    text_input_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_TEXT_INPUT_DELAY", 0.5
        )
    )
    keyboard_restore_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_KEYBOARD_RESTORE_DELAY", 0.5
        )
    )


@dataclass(slots=True)
class DeviceTimingConfig:
    default_tap_delay: float = field(
        default_factory=lambda: _env_non_negative_float("PHONE_AGENT_TAP_DELAY", 0.8)
    )
    default_double_tap_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_DOUBLE_TAP_DELAY", 0.8
        )
    )
    double_tap_interval: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_DOUBLE_TAP_INTERVAL", 0.12
        )
    )
    default_long_press_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_LONG_PRESS_DELAY", 0.8
        )
    )
    default_swipe_delay: float = field(
        default_factory=lambda: _env_non_negative_float("PHONE_AGENT_SWIPE_DELAY", 0.8)
    )
    default_back_delay: float = field(
        default_factory=lambda: _env_non_negative_float("PHONE_AGENT_BACK_DELAY", 0.8)
    )
    default_home_delay: float = field(
        default_factory=lambda: _env_non_negative_float("PHONE_AGENT_HOME_DELAY", 0.8)
    )
    default_launch_delay: float = field(
        default_factory=lambda: _env_non_negative_float("PHONE_AGENT_LAUNCH_DELAY", 1.2)
    )


@dataclass(slots=True)
class ConnectionTimingConfig:
    adb_restart_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_ADB_RESTART_DELAY", 2.0
        )
    )
    server_restart_delay: float = field(
        default_factory=lambda: _env_non_negative_float(
            "PHONE_AGENT_SERVER_RESTART_DELAY", 1.0
        )
    )


@dataclass(slots=True)
class TimingConfig:
    action: ActionTimingConfig = field(default_factory=ActionTimingConfig)
    device: DeviceTimingConfig = field(default_factory=DeviceTimingConfig)
    connection: ConnectionTimingConfig = field(default_factory=ConnectionTimingConfig)


TIMING_CONFIG = TimingConfig()


def get_timing_config() -> TimingConfig:
    return TIMING_CONFIG


def update_timing_config(
    action: ActionTimingConfig | None = None,
    device: DeviceTimingConfig | None = None,
    connection: ConnectionTimingConfig | None = None,
) -> None:
    if action is not None:
        TIMING_CONFIG.action = action
    if device is not None:
        TIMING_CONFIG.device = device
    if connection is not None:
        TIMING_CONFIG.connection = connection


__all__ = [
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "TimingConfig",
    "TIMING_CONFIG",
    "get_timing_config",
    "update_timing_config",
]
