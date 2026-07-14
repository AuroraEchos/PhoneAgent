"""Cached device application catalog and model-facing context builder."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from phoneagent.apps.aliases import extract_app_queries
from phoneagent.apps.discovery import AppDiscovery
from phoneagent.apps.models import AppResolution, InstalledApp
from phoneagent.apps.resolver import AppResolver


@dataclass(slots=True)
class AppCatalogConfig:
    ttl_seconds: float = 300.0
    refresh_on_start: bool = True
    max_prompt_matches: int = 5

    def __post_init__(self) -> None:
        if self.ttl_seconds < 0:
            raise ValueError("app catalog ttl_seconds cannot be negative")
        if self.max_prompt_matches < 0:
            raise ValueError("app prompt limit cannot be negative")


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
