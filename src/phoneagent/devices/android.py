"""Android device adapter backed by ADB."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from phoneagent.adb import device as adb_device
from phoneagent.adb.command import ADBCommandError, run_adb
from phoneagent.adb.screenshot import Screenshot, ScreenshotCaptureError, get_screenshot
from phoneagent.apps import (
    AppCatalog,
    AppCatalogConfig,
    AppDiscovery,
    AppDiscoveryConfig,
    AppLaunchResult,
    AppLauncherConfig,
    LaunchAppCapability,
)


class DeviceUnavailableError(RuntimeError):
    """Raised when the selected Android device is not ready for automation."""


@dataclass(slots=True)
class ScreenObservation:
    """Current phone observation used by the agent loop."""

    screenshot: Screenshot
    current_app: str
    current_package: str | None = None

    def to_screen_info(self) -> dict[str, Any]:
        """Return compact JSON-serializable metadata for the model prompt."""
        return {
            "current_app": self.current_app,
            "current_package": self.current_package,
            "screen_width": self.screenshot.display_width,
            "screen_height": self.screenshot.display_height,
            "image_width": self.screenshot.width,
            "image_height": self.screenshot.height,
            "image_mime_type": self.screenshot.mime_type,
            "coordinate_system": "relative_0_999",
            "screenshot_available": self.screenshot.available,
            "is_sensitive_screen": self.screenshot.is_sensitive,
            "is_blank_screen": self.screenshot.is_blank,
            "screenshot_sha256": self.screenshot.sha256,
            "observation_error": self.screenshot.error,
        }


class AndroidDevice:
    """A minimal Android-only device interface."""

    def __init__(
        self,
        device_id: str | None = None,
        *,
        allow_fallback_screenshot: bool = False,
        screenshot_max_size: int = 1280,
        screenshot_format: str = "JPEG",
        screenshot_quality: int = 90,
        app_catalog_config: AppCatalogConfig | None = None,
        app_discovery_config: AppDiscoveryConfig | None = None,
        app_launcher_config: AppLauncherConfig | None = None,
    ):
        self.device_id = device_id
        self.allow_fallback_screenshot = allow_fallback_screenshot
        self.screenshot_max_size = screenshot_max_size
        self.screenshot_format = screenshot_format
        self.screenshot_quality = screenshot_quality
        self.app_catalog = AppCatalog(
            AppDiscovery(device_id=device_id, config=app_discovery_config),
            config=app_catalog_config,
        )
        self.app_launcher = LaunchAppCapability(
            device=self,
            catalog=self.app_catalog,
            config=app_launcher_config,
        )

    def ensure_ready(self) -> None:
        """Verify that ADB can address a device in the ``device`` state."""
        try:
            result = run_adb(
                ["get-state"],
                device_id=self.device_id,
                timeout=5,
                check=False,
                retries=1,
            )
        except ADBCommandError as exc:
            raise DeviceUnavailableError(str(exc)) from exc
        state = (result.stdout or "").strip()
        if result.returncode != 0 or state != "device":
            details = ((result.stdout or "") + (result.stderr or "")).strip()
            raise DeviceUnavailableError(
                f"Android device is not ready (state={state or 'unknown'}): {details}"
            )

    def observe(self) -> ScreenObservation:
        """Capture a trustworthy current screen and focused application."""
        self.ensure_ready()
        try:
            screenshot = get_screenshot(
                self.device_id,
                max_size=self.screenshot_max_size,
                image_format=self.screenshot_format,
                quality=self.screenshot_quality,
                allow_fallback=self.allow_fallback_screenshot,
            )
        except ScreenshotCaptureError:
            raise

        if not screenshot.available and not self.allow_fallback_screenshot:
            raise ScreenshotCaptureError(screenshot.error or "Screenshot unavailable")

        try:
            current_app = adb_device.get_current_app(self.device_id)
        except (ADBCommandError, ValueError):
            current_app = "Unknown"
        current_package = self._package_from_current_app(current_app)
        if current_package and current_app.startswith("Unknown ("):
            discovered = self.app_catalog.find_by_package(current_package)
            if discovered is not None:
                current_app = discovered.display_name
        return ScreenObservation(
            screenshot=screenshot,
            current_app=current_app,
            current_package=current_package,
        )

    @staticmethod
    def _package_from_current_app(current_app: str) -> str | None:
        if current_app.startswith("Unknown (") and current_app.endswith(")"):
            return current_app[len("Unknown (") : -1]
        from phoneagent.config.apps import get_package_name

        return get_package_name(current_app)

    def tap(self, x: int, y: int) -> None:
        adb_device.tap(x, y, self.device_id)

    def double_tap(self, x: int, y: int) -> None:
        adb_device.double_tap(x, y, self.device_id)

    def long_press(self, x: int, y: int, duration_ms: int = 800) -> None:
        adb_device.long_press(x, y, duration_ms=duration_ms, device_id=self.device_id)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
    ) -> None:
        adb_device.swipe(
            start_x,
            start_y,
            end_x,
            end_y,
            duration_ms=duration_ms,
            device_id=self.device_id,
        )

    def back(self) -> None:
        adb_device.back(self.device_id)

    def home(self) -> None:
        adb_device.home(self.device_id)

    def launch_app_resolved(self, app_name: str) -> AppLaunchResult:
        """Resolve against the real device catalog and launch deterministically."""
        return self.app_launcher.launch(app_name)

    def launch_app(self, app_name: str) -> bool:
        """Compatibility wrapper returning whether launch or visual fallback started."""
        return self.launch_app_resolved(app_name).success

    def list_launchable_apps(self, *, refresh: bool = False):
        """Return launchable apps discovered on the connected device."""
        if refresh:
            return self.app_catalog.refresh()
        return self.app_catalog.ensure_loaded()

    def type_text(self, text: str) -> None:
        adb_device.type_text(text, self.device_id)

    def clear_text(self) -> None:
        adb_device.clear_text(self.device_id)

    def detect_and_set_adb_keyboard(self) -> str:
        return adb_device.detect_and_set_adb_keyboard(self.device_id)

    def restore_keyboard(self, ime: str) -> None:
        adb_device.restore_keyboard(ime, self.device_id)

    def send_keyevent(self, keycode: str | int) -> None:
        run_adb(
            ["shell", "input", "keyevent", keycode],
            device_id=self.device_id,
            timeout=5,
        )
