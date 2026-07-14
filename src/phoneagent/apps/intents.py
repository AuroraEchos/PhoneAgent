"""Conservative task intent helpers for deterministic application routing."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PureLaunchIntent:
    """A user task whose complete goal is to open one application."""

    query: str
    original_task: str


_TRAILING_PUNCTUATION = "。.!！?？"


def extract_pure_launch_intent(task: str) -> PureLaunchIntent | None:
    """Return a pure launch intent when no follow-up operation is present.

    The classifier is intentionally narrow.  It authorizes deterministic
    routing only when the whole user task is equivalent to opening one app.
    Multi-step requests such as ``打开力扣，然后搜索两数之和`` are excluded and
    continue through the normal model loop after app-context preparation.
    """

    text = str(task or "").strip()
    if not text:
        return None

    # Explicit multi-step separators make the task ineligible even when the
    # first clause is a launch request.
    if re.search(r"(?:然后|接着|随后|并且|并|再|，|,|；|;|\band\b|\bthen\b)", text, re.I):
        return None

    chinese = re.fullmatch(
        rf"\s*(?:请|麻烦)?\s*(?:帮我)?\s*(?:找到并)?(?:打开|启动|进入|运行)"
        rf"\s*(?:一下)?\s*(?:应用|app)?\s*[\"'“”]?(.+?)[\"'“”]?"
        rf"\s*(?:应用|app)?\s*[{re.escape(_TRAILING_PUNCTUATION)}]*\s*",
        text,
        flags=re.IGNORECASE,
    )
    if chinese:
        query = chinese.group(1).strip(" \t\r\n\"'“”")
        if 0 < len(query) <= 64:
            return PureLaunchIntent(query=query, original_task=text)

    english = re.fullmatch(
        rf"\s*(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(?:app\s+)?"
        rf"[\"']?(.+?)[\"']?\s*(?:app)?\s*[{re.escape(_TRAILING_PUNCTUATION)}]*\s*",
        text,
        flags=re.IGNORECASE,
    )
    if english:
        query = english.group(1).strip(" \t\r\n\"'")
        if 0 < len(query) <= 64:
            return PureLaunchIntent(query=query, original_task=text)
    return None
