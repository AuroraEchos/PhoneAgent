"""Configuration helpers for PhoneAgent."""

from __future__ import annotations

from typing import Any

from phoneagent.config.apps import APP_PACKAGES
from phoneagent.config.env import load_env
from phoneagent.config.messages import get_message, get_messages
from phoneagent.config.prompts_zh import SYSTEM_PROMPT as SYSTEM_PROMPT_ZH, build_system_prompt


def get_system_prompt() -> str:
    """Return the Chinese system prompt with the current local date."""
    return build_system_prompt()


SYSTEM_PROMPT = SYSTEM_PROMPT_ZH

__all__ = [
    "APP_PACKAGES",
    "load_env",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_ZH",
    "get_system_prompt",
    "build_system_prompt",
    "get_messages",
    "get_message",
    "TIMING_CONFIG",
    "TimingConfig",
    "ActionTimingConfig",
    "DeviceTimingConfig",
    "ConnectionTimingConfig",
    "get_timing_config",
    "update_timing_config",
]


def __getattr__(name: str) -> Any:
    if name in {
        "TIMING_CONFIG",
        "TimingConfig",
        "ActionTimingConfig",
        "DeviceTimingConfig",
        "ConnectionTimingConfig",
        "get_timing_config",
        "update_timing_config",
    }:
        from phoneagent.config import timing

        return getattr(timing, name)
    raise AttributeError(f"module 'phoneagent.config' has no attribute {name!r}")
