"""ADB-backed discovery of launchable Android applications."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.apps.aliases import canonical_alias, load_alias_file, package_aliases
from phoneagent.apps.models import InstalledApp


_COMPONENT_RE = re.compile(
    r"(?P<package>[A-Za-z][\w]*(?:\.[\w]+)+)/(?P<activity>[A-Za-z0-9_.$]+)"
)
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
            label_source = (
                "user_or_configured_alias" if label else "package"
            )
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
