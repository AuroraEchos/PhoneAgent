"""Deterministic and confidence-aware installed application resolution."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from phoneagent.apps.aliases import normalize_app_name
from phoneagent.apps.models import (
    AppCandidate,
    AppMatchType,
    AppResolution,
    InstalledApp,
)


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
            match_type = (
                AppMatchType.LABEL_EXACT
                if name == app.label
                else AppMatchType.ALIAS_EXACT
            )
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
