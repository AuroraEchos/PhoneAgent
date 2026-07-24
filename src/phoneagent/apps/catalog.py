"""Installed-app discovery, resolution, caching and task intent helpers.

The application domain is kept in one module because these pieces form one
cohesive research-runtime capability: discover launchable packages, resolve a
user query, cache the result, and expose only task-relevant candidates.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.apps.models import (
    AppCandidate,
    AppMatchType,
    AppResolution,
    InstalledApp,
)
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
        package: tuple(dict.fromkeys(aliases)) for package, aliases in grouped.items() if aliases
    }


_COMPONENT_RE = re.compile(r"(?P<package>[A-Za-z][\w]*(?:\.[\w]+)+)/(?P<activity>[A-Za-z0-9_.$]+)")
_LABEL_PATTERNS = (
    re.compile(r"application-label(?:-[^:]+)?:\s*['\"]?([^\r\n'\"]+)"),
    re.compile(r"nonLocalizedLabel=([^\r\n,}]+)"),
    re.compile(r"\blabel=([^\r\n,}]+)"),
)


class AppDiscoveryError(RuntimeError):
    """Raised when the device application catalog cannot be queried."""


@dataclass(slots=True)
class AppDiscoveryConfig:
    query_timeout_seconds: float = 20.0
    label_timeout_seconds: float = 3.0
    enrich_unknown_labels: bool = True
    max_label_queries: int = 4
    alias_file: str | None = field(
        default_factory=lambda: os.getenv("PHONE_AGENT_APP_ALIASES_FILE")
    )

    def __post_init__(self) -> None:
        if self.query_timeout_seconds <= 0 or self.label_timeout_seconds <= 0:
            raise ValueError("app discovery timeouts must be positive")
        if self.max_label_queries < 0:
            raise ValueError("max_label_queries cannot be negative")


class AppDiscovery:
    """Discover launcher activities using PackageManager shell commands.

    Package/activity components are treated as authoritative. Display labels are
    best-effort because Android's shell interface does not expose a stable,
    cross-version label-only command.
    """

    def __init__(
        self,
        device_id: str | None = None,
        config: AppDiscoveryConfig | None = None,
    ) -> None:
        self.device_id = device_id
        self.config = config or AppDiscoveryConfig()
        configured = package_aliases()
        custom = load_alias_file(self.config.alias_file)
        merged: dict[str, tuple[str, ...]] = {}
        for package in set(configured) | set(custom):
            merged[package] = tuple(
                dict.fromkeys((*custom.get(package, ()), *configured.get(package, ())))
            )
        self._aliases = merged

    def list_launchable_apps(self) -> list[InstalledApp]:
        output = self._query_launcher_components()
        components = self.parse_launcher_components(output)
        if not components:
            raise AppDiscoveryError("PackageManager returned no launcher activities")

        apps: list[InstalledApp] = []
        label_queries = 0
        for package_name, activity_name in components:
            aliases = self._aliases.get(package_name, ())
            label = aliases[0] if aliases else canonical_alias(package_name)
            label_source = "user_or_configured_alias" if label else "package"
            if (
                not label
                and self.config.enrich_unknown_labels
                and label_queries < self.config.max_label_queries
            ):
                label_queries += 1
                discovered_label = self.get_application_label(package_name)
                if discovered_label:
                    label = discovered_label
                    label_source = "dumpsys_best_effort"
            if not label:
                label = self._derive_label(package_name)
            apps.append(
                InstalledApp(
                    label=label,
                    package_name=package_name,
                    activity_name=activity_name,
                    aliases=aliases,
                    label_source=label_source,
                    launchable=True,
                )
            )
        return apps

    def get_application_label(self, package_name: str) -> str | None:
        result = run_adb(
            ["shell", "dumpsys", "package", package_name],
            device_id=self.device_id,
            timeout=self.config.label_timeout_seconds,
            check=False,
            retries=1,
        )
        if result.returncode != 0:
            return None
        return self.parse_application_label(result.stdout or "")

    def _query_launcher_components(self) -> str:
        commands = (
            [
                "shell",
                "cmd",
                "package",
                "query-activities",
                "--components",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
            ],
            [
                "shell",
                "pm",
                "query-activities",
                "--components",
                "-a",
                "android.intent.action.MAIN",
                "-c",
                "android.intent.category.LAUNCHER",
            ],
        )
        failures: list[str] = []
        for command in commands:
            try:
                result = run_adb(
                    command,
                    device_id=self.device_id,
                    timeout=self.config.query_timeout_seconds,
                    check=False,
                    retries=1,
                )
            except ADBCommandError as exc:
                failures.append(str(exc))
                continue
            output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
            if result.returncode == 0 and self.parse_launcher_components(output):
                return output
            failures.append(output or f"exit code {result.returncode}")
        raise AppDiscoveryError(
            "Unable to query launcher applications: " + " | ".join(failures[-2:])
        )

    @staticmethod
    def parse_launcher_components(output: str) -> list[tuple[str, str]]:
        seen: set[str] = set()
        components: list[tuple[str, str]] = []
        for match in _COMPONENT_RE.finditer(str(output or "")):
            package_name = match.group("package")
            activity_name = match.group("activity")
            component = f"{package_name}/{activity_name}"
            if component in seen:
                continue
            seen.add(component)
            components.append((package_name, activity_name))
        return components

    @staticmethod
    def parse_application_label(output: str) -> str | None:
        for pattern in _LABEL_PATTERNS:
            match = pattern.search(str(output or ""))
            if not match:
                continue
            label = match.group(1).strip().strip("'\"")
            if label and not label.startswith("0x") and len(label) <= 128:
                return label
        return None

    @staticmethod
    def _derive_label(package_name: str) -> str:
        parts = [part for part in package_name.split(".") if part]
        if not parts:
            return package_name
        ignored = {"com", "org", "net", "cn", "android", "app", "apps", "mobile"}
        candidates = [part for part in parts if part.casefold() not in ignored]
        value = candidates[-1] if candidates else parts[-1]
        return value.replace("_", " ").replace("-", " ")


@dataclass(slots=True)
class AppResolverConfig:
    accept_confidence: float = 0.86
    ambiguous_margin: float = 0.08
    fuzzy_threshold: float = 0.72
    max_alternatives: int = 5

    def __post_init__(self) -> None:
        for name in ("accept_confidence", "ambiguous_margin", "fuzzy_threshold"):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in the 0..1 range")
        if self.max_alternatives < 1:
            raise ValueError("max_alternatives must be positive")


class AppResolver:
    """Resolve an app query against a concrete device catalog."""

    def __init__(self, config: AppResolverConfig | None = None) -> None:
        self.config = config or AppResolverConfig()

    def resolve(self, query: str, apps: list[InstalledApp]) -> AppResolution:
        raw_query = str(query or "").strip()
        normalized_query = normalize_app_name(raw_query)
        if not normalized_query:
            return AppResolution(
                query=raw_query,
                matched_app=None,
                confidence=0.0,
                match_type=AppMatchType.NONE,
                reason="Application query is empty",
            )

        candidates = self._score_candidates(raw_query, normalized_query, apps)
        if not candidates:
            return AppResolution(
                query=raw_query,
                matched_app=None,
                confidence=0.0,
                match_type=AppMatchType.NONE,
                reason="No installed application matched the query",
            )

        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        exact = best.match_type in {
            AppMatchType.PACKAGE_EXACT,
            AppMatchType.ALIAS_EXACT,
            AppMatchType.LABEL_EXACT,
            AppMatchType.NORMALIZED_EXACT,
        }
        separated = second is None or best.score - second.score >= self.config.ambiguous_margin
        if exact or (best.score >= self.config.accept_confidence and separated):
            return AppResolution(
                query=raw_query,
                matched_app=best.app,
                confidence=best.score,
                match_type=best.match_type,
                matched_name=best.matched_name,
                alternatives=tuple(candidates[1 : self.config.max_alternatives]),
                reason="Resolved to one installed application",
            )

        alternatives = tuple(
            candidate
            for candidate in candidates[: self.config.max_alternatives]
            if candidate.score >= self.config.fuzzy_threshold
        )
        if alternatives:
            return AppResolution(
                query=raw_query,
                matched_app=None,
                confidence=best.score,
                match_type=AppMatchType.NONE,
                alternatives=alternatives,
                reason="Multiple or low-confidence installed applications matched",
            )
        return AppResolution(
            query=raw_query,
            matched_app=None,
            confidence=best.score,
            match_type=AppMatchType.NONE,
            reason="Best match did not meet the confidence threshold",
        )

    def rank(self, query: str, apps: list[InstalledApp], limit: int = 5) -> list[AppCandidate]:
        normalized = normalize_app_name(query)
        if not normalized:
            return []
        return self._score_candidates(query, normalized, apps)[: max(0, limit)]

    def _score_candidates(
        self,
        raw_query: str,
        normalized_query: str,
        apps: list[InstalledApp],
    ) -> list[AppCandidate]:
        best_by_package: dict[str, AppCandidate] = {}
        for app in apps:
            for name in app.names():
                candidate = self._score_name(raw_query, normalized_query, app, name)
                if candidate is None:
                    continue
                previous = best_by_package.get(app.package_name)
                if previous is None or candidate.score > previous.score:
                    best_by_package[app.package_name] = candidate
        return sorted(
            best_by_package.values(),
            key=lambda item: (-item.score, item.app.display_name.casefold(), item.app.package_name),
        )

    def _score_name(
        self,
        raw_query: str,
        normalized_query: str,
        app: InstalledApp,
        name: str,
    ) -> AppCandidate | None:
        normalized_name = normalize_app_name(name)
        if not normalized_name:
            return None
        if raw_query == app.package_name:
            return AppCandidate(app, 1.0, AppMatchType.PACKAGE_EXACT, name)
        if raw_query.casefold() == name.casefold():
            match_type = AppMatchType.LABEL_EXACT if name == app.label else AppMatchType.ALIAS_EXACT
            return AppCandidate(app, 0.99, match_type, name)
        if normalized_query == normalized_name:
            return AppCandidate(app, 0.97, AppMatchType.NORMALIZED_EXACT, name)
        if normalized_query in normalized_name or normalized_name in normalized_query:
            shorter = min(len(normalized_query), len(normalized_name))
            longer = max(len(normalized_query), len(normalized_name))
            score = 0.82 + 0.12 * (shorter / max(1, longer))
            return AppCandidate(app, min(score, 0.94), AppMatchType.SUBSTRING, name)
        ratio = SequenceMatcher(None, normalized_query, normalized_name).ratio()
        if ratio >= self.config.fuzzy_threshold:
            return AppCandidate(app, ratio, AppMatchType.FUZZY, name)
        return None


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


@dataclass(slots=True)
class AppCatalogConfig:
    ttl_seconds: float = 300.0
    refresh_on_start: bool = True
    max_prompt_matches: int = 5
    prompt_char_budget: int = 6000

    def __post_init__(self) -> None:
        if self.ttl_seconds < 0:
            raise ValueError("app catalog ttl_seconds cannot be negative")
        if self.max_prompt_matches < 0:
            raise ValueError("app prompt limit cannot be negative")
        if self.prompt_char_budget < 256:
            raise ValueError("app prompt_char_budget must be at least 256")


class AppCatalog:
    """A bounded cache over launcher applications on one Android device."""

    def __init__(
        self,
        discovery: AppDiscovery,
        resolver: AppResolver | None = None,
        config: AppCatalogConfig | None = None,
    ) -> None:
        self.discovery = discovery
        self.resolver = resolver or AppResolver()
        self.config = config or AppCatalogConfig()
        self._apps: list[InstalledApp] = []
        self._refreshed_at: float | None = None
        self._last_error: str | None = None

    @property
    def apps(self) -> list[InstalledApp]:
        return list(self._apps)

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def refreshed_at(self) -> float | None:
        return self._refreshed_at

    @property
    def stale(self) -> bool:
        if self._refreshed_at is None:
            return True
        if self.config.ttl_seconds == 0:
            return True
        return time.time() - self._refreshed_at >= self.config.ttl_seconds

    def refresh(self, *, raise_on_error: bool = False) -> list[InstalledApp]:
        try:
            apps = self.discovery.list_launchable_apps()
        except Exception as exc:
            self._last_error = str(exc)
            if raise_on_error:
                raise
            return self.apps
        self._apps = sorted(
            apps,
            key=lambda app: (app.display_name.casefold(), app.package_name),
        )
        self._refreshed_at = time.time()
        self._last_error = None
        return self.apps

    def ensure_loaded(self) -> list[InstalledApp]:
        if not self._apps or self.stale:
            self.refresh()
        return self.apps

    def resolve(self, query: str, *, refresh_if_missing: bool = True) -> AppResolution:
        apps = self.ensure_loaded()
        resolution = self.resolver.resolve(query, apps)
        if not resolution.matched and refresh_if_missing:
            previous_refresh = self._refreshed_at
            self.refresh()
            if self._refreshed_at != previous_refresh:
                resolution = self.resolver.resolve(query, self._apps)
        return resolution

    def find_by_package(self, package_name: str) -> InstalledApp | None:
        query = str(package_name or "").strip()
        for app in self.ensure_loaded():
            if app.package_name == query:
                return app
        return None

    def build_prompt_context(self, goal: str) -> dict[str, Any]:
        apps = self.ensure_loaded()
        queries = extract_app_queries(goal)
        likely: list[dict[str, Any]] = []
        for query in queries:
            ranked = self.resolver.rank(query, apps, self.config.max_prompt_matches)
            resolution = self.resolver.resolve(query, apps)
            likely.append(
                {
                    "query": query,
                    "resolution": resolution.to_dict(),
                    "candidates": [candidate.to_dict() for candidate in ranked],
                }
            )
        return {
            "catalog_available": bool(apps),
            "installed_launchable_count": len(apps),
            "catalog_refreshed_at": self._refreshed_at,
            "catalog_error": self._last_error,
            "likely_goal_apps": likely,
            "context_policy": "task_relevant_top_k_only",
            "max_candidates_per_query": self.config.max_prompt_matches,
            "launch_policy": (
                "Use the unique high-confidence resolution when one is supplied. Do not "
                "enumerate or reconstruct the complete installed-app catalog. Runtime "
                "starts resolved packages directly; desktop folders are irrelevant. "
                "Do not invent an app when candidates are ambiguous."
            ),
        }
