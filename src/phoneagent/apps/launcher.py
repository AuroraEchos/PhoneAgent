"""Deterministic application launch capability with bounded visual fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.apps.catalog import AppCatalog
from phoneagent.apps.models import (
    AppLaunchFailureReason,
    AppLaunchResult,
    AppLaunchStatus,
    InstalledApp,
)


class LauncherDevice(Protocol):
    device_id: str | None

    def home(self) -> None: ...
    def type_text(self, text: str) -> None: ...


@dataclass(slots=True)
class AppLauncherConfig:
    direct_launch_timeout_seconds: float = 15.0
    enable_launcher_search_fallback: bool = True
    launcher_search_keycode: str = "KEYCODE_SEARCH"

    def __post_init__(self) -> None:
        if self.direct_launch_timeout_seconds <= 0:
            raise ValueError("direct_launch_timeout_seconds must be positive")


class LaunchAppCapability:
    """Resolve and start an installed app without desktop icon navigation."""

    def __init__(
        self,
        device: LauncherDevice,
        catalog: AppCatalog,
        config: AppLauncherConfig | None = None,
    ) -> None:
        self.device = device
        self.catalog = catalog
        self.config = config or AppLauncherConfig()

    def launch(self, query: str) -> AppLaunchResult:
        raw_query = str(query or "").strip()
        resolution = self.catalog.resolve(raw_query, refresh_if_missing=False)
        refreshed = False
        if not resolution.matched and not resolution.ambiguous:
            before = self.catalog.refreshed_at
            self.catalog.refresh()
            refreshed = self.catalog.refreshed_at != before
            resolution = self.catalog.resolve(raw_query, refresh_if_missing=False)

        if resolution.ambiguous:
            return AppLaunchResult(
                status=AppLaunchStatus.AMBIGUOUS,
                query=raw_query,
                resolution=resolution,
                message="Application name is ambiguous; select one explicit candidate",
                failure_reason=AppLaunchFailureReason.APP_NAME_AMBIGUOUS,
                catalog_refreshed=refreshed,
            )
        if resolution.matched_app is None:
            if self.config.enable_launcher_search_fallback and raw_query:
                fallback = self._prepare_launcher_search(raw_query)
                if fallback:
                    return AppLaunchResult(
                        status=AppLaunchStatus.VISUAL_SEARCH_READY,
                        query=raw_query,
                        resolution=resolution,
                        message=(
                            "No confident package match. Launcher search was opened and "
                            "the query was entered; the model must visually verify and tap "
                            "the correct result."
                        ),
                        failure_reason=AppLaunchFailureReason.VISUAL_SEARCH_REQUIRED,
                        catalog_refreshed=refreshed,
                        metadata={"fallback": "launcher_search"},
                    )
            return AppLaunchResult(
                status=AppLaunchStatus.NOT_FOUND,
                query=raw_query,
                resolution=resolution,
                message=f"No launchable installed application matched {raw_query!r}",
                failure_reason=AppLaunchFailureReason.APP_NOT_DISCOVERED,
                catalog_refreshed=refreshed,
            )

        app = resolution.matched_app
        if not app.launchable:
            return AppLaunchResult(
                status=AppLaunchStatus.NOT_LAUNCHABLE,
                query=raw_query,
                resolution=resolution,
                app=app,
                message=f"Package {app.package_name} has no launchable activity",
                failure_reason=AppLaunchFailureReason.PACKAGE_NOT_LAUNCHABLE,
                catalog_refreshed=refreshed,
            )
        try:
            self._direct_launch(app)
        except Exception as exc:
            return AppLaunchResult(
                status=AppLaunchStatus.COMMAND_FAILED,
                query=raw_query,
                resolution=resolution,
                app=app,
                message=f"Failed to launch {app.display_name}: {exc}",
                failure_reason=AppLaunchFailureReason.LAUNCH_COMMAND_FAILED,
                direct_launch_attempted=True,
                catalog_refreshed=refreshed,
                metadata={"exception_type": type(exc).__name__},
            )
        return AppLaunchResult(
            status=AppLaunchStatus.LAUNCHED,
            query=raw_query,
            resolution=resolution,
            app=app,
            message=f"Launched {app.display_name} ({app.package_name})",
            direct_launch_attempted=True,
            catalog_refreshed=refreshed,
            metadata={"launch_mode": "component" if app.component_name else "monkey"},
        )

    def _direct_launch(self, app: InstalledApp) -> None:
        if app.component_name:
            result = run_adb(
                ["shell", "am", "start", "-W", "-n", app.component_name],
                device_id=self.device.device_id,
                timeout=self.config.direct_launch_timeout_seconds,
                check=False,
            )
            output = f"{result.stdout or ''}\n{result.stderr or ''}".casefold()
            failed = (
                result.returncode != 0
                or "error:" in output
                or "exception" in output
                or "unable to resolve" in output
            )
            if not failed:
                return
        result = run_adb(
            [
                "shell",
                "monkey",
                "-p",
                app.package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            device_id=self.device.device_id,
            timeout=self.config.direct_launch_timeout_seconds,
            check=False,
        )
        output = f"{result.stdout or ''}\n{result.stderr or ''}".casefold()
        if (
            result.returncode != 0
            or "no activities found" in output
            or "monkey aborted" in output
            or "permission denied" in output
        ):
            raise ADBCommandError(
                result.args,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                reason=f"failed to launch package {app.package_name}",
            )

    def _prepare_launcher_search(self, query: str) -> bool:
        try:
            self.device.home()
            result = run_adb(
                ["shell", "input", "keyevent", self.config.launcher_search_keycode],
                device_id=self.device.device_id,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return False
            self.device.type_text(query)
            return True
        except Exception:
            return False
