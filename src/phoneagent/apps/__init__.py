"""Device application awareness for PhoneAgent."""

from phoneagent.apps.aliases import (
    canonical_alias,
    extract_app_queries,
    load_alias_file,
    normalize_app_name,
)
from phoneagent.apps.catalog import AppCatalog, AppCatalogConfig
from phoneagent.apps.discovery import AppDiscovery, AppDiscoveryConfig, AppDiscoveryError
from phoneagent.apps.launcher import AppLauncherConfig, LaunchAppCapability
from phoneagent.apps.intents import PureLaunchIntent, extract_pure_launch_intent
from phoneagent.apps.models import (
    AppCandidate,
    AppLaunchFailureReason,
    AppLaunchResult,
    AppLaunchStatus,
    AppMatchType,
    AppResolution,
    InstalledApp,
)
from phoneagent.apps.resolver import AppResolver, AppResolverConfig

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
