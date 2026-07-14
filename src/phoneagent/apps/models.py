"""Domain models for device application awareness and launching."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AppMatchType(str, Enum):
    """How a user-facing application query was resolved."""

    PACKAGE_EXACT = "package_exact"
    ALIAS_EXACT = "alias_exact"
    LABEL_EXACT = "label_exact"
    NORMALIZED_EXACT = "normalized_exact"
    SUBSTRING = "substring"
    FUZZY = "fuzzy"
    NONE = "none"


class AppLaunchStatus(str, Enum):
    """Outcome of an application launch request."""

    LAUNCHED = "launched"
    VISUAL_SEARCH_READY = "visual_search_ready"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    NOT_LAUNCHABLE = "not_launchable"
    COMMAND_FAILED = "command_failed"


class AppLaunchFailureReason(str, Enum):
    """Stable failure categories used by recovery and evaluation."""

    APP_NOT_INSTALLED = "app_not_installed"
    APP_NOT_DISCOVERED = "app_not_discovered"
    APP_NAME_AMBIGUOUS = "app_name_ambiguous"
    PACKAGE_NOT_LAUNCHABLE = "package_not_launchable"
    LAUNCH_COMMAND_FAILED = "launch_command_failed"
    LAUNCHER_SEARCH_FAILED = "launcher_search_failed"
    FOREGROUND_VERIFICATION_FAILED = "foreground_verification_failed"
    VISUAL_SEARCH_REQUIRED = "visual_search_required"


@dataclass(frozen=True, slots=True)
class InstalledApp:
    """One launchable application discovered on the connected Android device."""

    label: str
    package_name: str
    activity_name: str | None = None
    aliases: tuple[str, ...] = ()
    label_source: str = "package"
    launchable: bool = True
    system_app: bool | None = None

    @property
    def component_name(self) -> str | None:
        if not self.activity_name:
            return None
        if "/" in self.activity_name:
            return self.activity_name
        return f"{self.package_name}/{self.activity_name}"

    @property
    def display_name(self) -> str:
        return self.label or self.package_name

    def names(self) -> tuple[str, ...]:
        values = [self.label, self.package_name, *self.aliases]
        return tuple(dict.fromkeys(value for value in values if value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "package_name": self.package_name,
            "activity_name": self.activity_name,
            "component_name": self.component_name,
            "aliases": list(self.aliases),
            "label_source": self.label_source,
            "launchable": self.launchable,
            "system_app": self.system_app,
        }


@dataclass(frozen=True, slots=True)
class AppCandidate:
    """A scored application candidate returned by the resolver."""

    app: InstalledApp
    score: float
    match_type: AppMatchType
    matched_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app.to_dict(),
            "score": round(float(self.score), 4),
            "match_type": self.match_type.value,
            "matched_name": self.matched_name,
        }


@dataclass(frozen=True, slots=True)
class AppResolution:
    """Resolution of user language to an installed application."""

    query: str
    matched_app: InstalledApp | None
    confidence: float
    match_type: AppMatchType
    matched_name: str = ""
    alternatives: tuple[AppCandidate, ...] = ()
    reason: str = ""

    @property
    def matched(self) -> bool:
        return self.matched_app is not None

    @property
    def ambiguous(self) -> bool:
        return not self.matched and bool(self.alternatives)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "matched": self.matched,
            "ambiguous": self.ambiguous,
            "matched_app": self.matched_app.to_dict() if self.matched_app else None,
            "confidence": round(float(self.confidence), 4),
            "match_type": self.match_type.value,
            "matched_name": self.matched_name,
            "alternatives": [candidate.to_dict() for candidate in self.alternatives],
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AppLaunchResult:
    """Structured result from deterministic launch or launcher-search fallback."""

    status: AppLaunchStatus
    query: str
    resolution: AppResolution | None = None
    app: InstalledApp | None = None
    message: str = ""
    failure_reason: AppLaunchFailureReason | None = None
    direct_launch_attempted: bool = False
    catalog_refreshed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status in {
            AppLaunchStatus.LAUNCHED,
            AppLaunchStatus.VISUAL_SEARCH_READY,
        }

    @property
    def fully_launched(self) -> bool:
        return self.status is AppLaunchStatus.LAUNCHED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "query": self.query,
            "success": self.success,
            "fully_launched": self.fully_launched,
            "message": self.message,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "direct_launch_attempted": self.direct_launch_attempted,
            "catalog_refreshed": self.catalog_refreshed,
            "resolution": self.resolution.to_dict() if self.resolution else None,
            "app": self.app.to_dict() if self.app else None,
            "metadata": dict(self.metadata),
        }
