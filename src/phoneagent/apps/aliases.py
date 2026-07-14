"""Alias normalization and compatibility helpers for application names."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

from phoneagent.config.apps import APP_PACKAGES


def normalize_app_name(value: str) -> str:
    """Normalize human application names without destroying CJK characters."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = re.sub(r"[\s\-_.·•:：/\\()（）\[\]【】]+", "", text)
    return text


def package_aliases() -> dict[str, tuple[str, ...]]:
    """Return all configured aliases grouped by Android package."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for alias, package in APP_PACKAGES.items():
        if alias not in grouped[package]:
            grouped[package].append(alias)
    return {package: tuple(aliases) for package, aliases in grouped.items()}


def canonical_alias(package_name: str) -> str | None:
    aliases = package_aliases().get(package_name, ())
    return aliases[0] if aliases else None


def extract_app_queries(task: str) -> list[str]:
    """Extract likely application names from a natural-language task.

    This is deliberately conservative. It only produces hints for the model and
    resolver; it never authorizes an action by itself.
    """
    text = str(task or "").strip()
    if not text:
        return []

    patterns = (
        r"(?:找到并)?(?:打开|启动|进入|运行)\s*(?:一下|应用|app)?\s*[\"'“”]?(.+?)(?=然后|并且|并|，|,|。|；|;|$)",
        r"(?:open|launch|start)\s+(?:the\s+)?(?:app\s+)?[\"']?(.+?)(?=\s+and\s+|,|\.|;|$)",
    )
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).strip(" \t\r\n\"'“”")
            value = re.sub(r"^(?:我的|这个|那个)", "", value).strip()
            if 0 < len(value) <= 64 and value not in candidates:
                candidates.append(value)
    return candidates


def load_alias_file(path: str | None) -> dict[str, tuple[str, ...]]:
    """Load optional user aliases from JSON.

    Supported forms:
      * ``{"力扣": "com.leetcode..."}`` (alias -> package)
      * ``{"com.leetcode...": ["力扣", "LeetCode"]}`` (package -> aliases)
    Invalid entries are ignored; malformed JSON raises ``ValueError``.
    """
    if not path:
        return {}
    alias_path = Path(path).expanduser()
    if not alias_path.exists():
        return {}
    try:
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to load app alias file {alias_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("App alias file must contain a JSON object")

    grouped: dict[str, list[str]] = defaultdict(list)
    for key, value in payload.items():
        if isinstance(value, str):
            alias = str(key).strip()
            package = value.strip()
            if alias and package:
                grouped[package].append(alias)
        elif isinstance(value, list):
            package = str(key).strip()
            for item in value:
                alias = str(item).strip()
                if package and alias:
                    grouped[package].append(alias)
    return {
        package: tuple(dict.fromkeys(aliases))
        for package, aliases in grouped.items()
        if aliases
    }
