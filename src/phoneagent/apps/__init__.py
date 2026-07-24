"""Installed application awareness and deterministic launch capability."""

from phoneagent.apps.catalog import (
    AppCatalog,
    AppCatalogConfig,
    AppDiscovery,
    AppDiscoveryConfig,
    AppDiscoveryError,
    AppResolver,
    AppResolverConfig,
    PureLaunchIntent,
    canonical_alias,
    extract_app_queries,
    extract_pure_launch_intent,
    load_alias_file,
    normalize_app_name,
)
from phoneagent.apps.launcher import AppLauncherConfig, LaunchAppCapability
from phoneagent.apps.models import (
    AppCandidate,
    AppLaunchFailureReason,
    AppLaunchResult,
    AppLaunchStatus,
    AppMatchType,
    AppResolution,
    InstalledApp,
)

__all__ = [
    "AppCandidate",
    "AppCatalog",
    "AppCatalogConfig",
    "AppDiscovery",
    "AppDiscoveryConfig",
    "AppDiscoveryError",
    "AppLaunchFailureReason",
    "AppLaunchResult",
    "AppLaunchStatus",
    "AppLauncherConfig",
    "AppMatchType",
    "AppResolution",
    "AppResolver",
    "AppResolverConfig",
    "InstalledApp",
    "LaunchAppCapability",
    "PureLaunchIntent",
    "canonical_alias",
    "extract_app_queries",
    "extract_pure_launch_intent",
    "load_alias_file",
    "normalize_app_name",
]
