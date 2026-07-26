"""Narrow, auditable adapters for provider-specific action syntax."""

from __future__ import annotations

import re
from collections.abc import Callable

_NUMBER = r"(?:\d+(?:\.\d+)?)"
_POINT_TAG = (
    rf"<(?P<tag>point|point_2d)>\s*"
    rf"(?:[\[(]\s*)?(?P<x>{_NUMBER})\s*(?:,|\s)\s*(?P<y>{_NUMBER})"
    rf"(?:\s*[\])])?\s*</(?P=tag)>"
)
_SPECIAL_POINT_TAG = (
    rf"<\|point_start\|>\s*(?:[\[(]\s*)?"
    rf"(?P<x>{_NUMBER})\s*(?:,|\s)\s*(?P<y>{_NUMBER})"
    rf"(?:\s*[\])])?\s*<\|point_end\|>"
)
_COORDINATE_PREFIX = r"(?P<prefix>\b(?:element|start|end)\s*=\s*)"


def _coordinate_patterns(point_pattern: str) -> tuple[re.Pattern[str], ...]:
    return (
        re.compile(
            _COORDINATE_PREFIX + rf"\[\s*{point_pattern}\s*\]",
            re.IGNORECASE,
        ),
        re.compile(
            _COORDINATE_PREFIX + rf"(?P<quote>['\"])\s*{point_pattern}\s*(?P=quote)",
            re.IGNORECASE,
        ),
        re.compile(_COORDINATE_PREFIX + point_pattern, re.IGNORECASE),
    )


_XML_POINT_PATTERNS = _coordinate_patterns(_POINT_TAG)
_SPECIAL_POINT_PATTERNS = _coordinate_patterns(_SPECIAL_POINT_TAG)
_POINT_MARKER_RE = re.compile(
    r"</?(?:point(?:_2d)?|box|bbox(?:_2d)?)>"
    r"|<\|(?:point|box)_(?:start|end)\|>",
    re.IGNORECASE,
)


def normalize_provider_action_syntax(text: str) -> str:
    """Canonicalize allowlisted provider syntax without inferring an action.

    Only explicit two-number point markers attached to known coordinate
    keywords are converted. Unknown tags, boxes, multiple points, non-numeric
    values and all other model output remain untouched for the strict parser to
    reject.
    """
    normalized = text
    adapters: tuple[Callable[[str], str], ...] = (
        _normalize_xml_point_coordinates,
        _normalize_special_point_coordinates,
    )
    for adapter in adapters:
        normalized = adapter(normalized)
    return normalized


def has_provider_coordinate_marker(text: str | None) -> bool:
    """Whether rejected output contains a recognized point marker."""
    return bool(text and _POINT_MARKER_RE.search(text))


def _normalize_xml_point_coordinates(text: str) -> str:
    return _apply_coordinate_patterns(text, _XML_POINT_PATTERNS)


def _normalize_special_point_coordinates(text: str) -> str:
    return _apply_coordinate_patterns(text, _SPECIAL_POINT_PATTERNS)


def _apply_coordinate_patterns(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    normalized = text
    for pattern in patterns:
        normalized = pattern.sub(
            lambda match: (
                _replace_point(match)
                if _is_outside_quoted_string(normalized, match.start())
                else match.group(0)
            ),
            normalized,
        )
    return normalized


def _replace_point(match: re.Match[str]) -> str:
    return f"{match.group('prefix')}[{match.group('x')}, {match.group('y')}]"


def _is_outside_quoted_string(text: str, position: int) -> bool:
    quote: str | None = None
    escaped = False
    for char in text[:position]:
        if quote is None:
            if char in {'"', "'"}:
                quote = char
            continue
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            quote = None
    return quote is None
