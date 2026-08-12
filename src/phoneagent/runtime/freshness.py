"""Optimistic concurrency guard for screenshot-bound device actions.

The model plans against one screenshot while the live Android UI may continue
to change.  This module compares that planning observation with a fresh
pre-dispatch observation and invalidates coordinate actions when their visual
precondition no longer holds.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageChops, ImageStat

from phoneagent.devices import ScreenObservation


_COORDINATE_ACTIONS = {"Tap", "Double Tap", "Long Press", "Swipe"}


@dataclass(slots=True)
class FreshnessConfig:
    """Thresholds for pre-dispatch screenshot compatibility."""

    enabled: bool = True
    observation_retries: int = 0
    observation_retry_delay: float = 0.1
    image_compare_width: int = 256
    target_radius_x_ratio: float = 0.10
    target_radius_y_ratio: float = 0.05
    pixel_delta_threshold: float = 0.08
    target_mean_difference_threshold: float = 0.025
    target_changed_pixel_ratio_threshold: float = 0.15
    # Global change is only a last-resort full-screen replacement signal. Dynamic
    # feeds and video often replace much of the content while leaving a stable
    # navigation target valid, so ordinary broad motion must not override an
    # unchanged target region.
    global_mean_difference_threshold: float = 0.15
    global_changed_pixel_ratio_threshold: float = 0.80
    crop_top_ratio: float = 0.04
    crop_bottom_ratio: float = 0.04

    def __post_init__(self) -> None:
        if self.image_compare_width < 64:
            raise ValueError("freshness image_compare_width must be at least 64")
        if self.observation_retries < 0:
            raise ValueError("freshness observation_retries cannot be negative")
        if self.observation_retry_delay < 0:
            raise ValueError("freshness observation_retry_delay cannot be negative")
        for name in (
            "target_radius_x_ratio",
            "target_radius_y_ratio",
            "pixel_delta_threshold",
            "target_mean_difference_threshold",
            "target_changed_pixel_ratio_threshold",
            "global_mean_difference_threshold",
            "global_changed_pixel_ratio_threshold",
            "crop_top_ratio",
            "crop_bottom_ratio",
        ):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"freshness {name} must be in the range [0, 1]")
        if self.target_radius_x_ratio <= 0 or self.target_radius_y_ratio <= 0:
            raise ValueError("freshness target radii must be positive")
        if self.pixel_delta_threshold <= 0:
            raise ValueError("freshness pixel_delta_threshold must be positive")
        if self.crop_top_ratio + self.crop_bottom_ratio >= 0.8:
            raise ValueError("freshness crop ratios leave too little image content")


@dataclass(slots=True)
class FreshnessResult:
    """Evidence from one optimistic pre-dispatch compatibility check."""

    checked: bool
    fresh: bool
    reason: str
    planned_capture_age_seconds: float | None = None
    fresh_capture_age_seconds: float | None = None
    check_duration_seconds: float | None = None
    app_changed: bool = False
    system_panel_changed: bool = False
    dimensions_changed: bool = False
    global_mean_difference: float | None = None
    global_changed_pixel_ratio: float | None = None
    target_mean_difference: float | None = None
    target_changed_pixel_ratio: float | None = None
    target_regions: int = 0
    comparison_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "fresh": self.fresh,
            "reason": self.reason,
            "planned_capture_age_seconds": self.planned_capture_age_seconds,
            "fresh_capture_age_seconds": self.fresh_capture_age_seconds,
            "check_duration_seconds": self.check_duration_seconds,
            "app_changed": self.app_changed,
            "system_panel_changed": self.system_panel_changed,
            "dimensions_changed": self.dimensions_changed,
            "global_mean_difference": self.global_mean_difference,
            "global_changed_pixel_ratio": self.global_changed_pixel_ratio,
            "target_mean_difference": self.target_mean_difference,
            "target_changed_pixel_ratio": self.target_changed_pixel_ratio,
            "target_regions": self.target_regions,
            "comparison_error": self.comparison_error,
        }


class ObservationFreshnessGuard:
    """Reject a coordinate action when its planning screenshot became stale."""

    def __init__(self, config: FreshnessConfig | None = None):
        self.config = config or FreshnessConfig()

    def requires_check(self, action: dict[str, Any]) -> bool:
        return bool(
            self.config.enabled
            and action.get("_metadata") == "do"
            and str(action.get("action", "")) in _COORDINATE_ACTIONS
        )

    def check(
        self,
        *,
        action: dict[str, Any],
        planned: ScreenObservation,
        current: ScreenObservation,
    ) -> FreshnessResult:
        """Compare the planned and current visual preconditions."""
        started = time.monotonic()
        result = FreshnessResult(
            checked=self.requires_check(action),
            fresh=True,
            reason="freshness_check_not_required",
            planned_capture_age_seconds=self._capture_age(planned),
            fresh_capture_age_seconds=self._capture_age(current),
        )
        if not result.checked:
            result.check_duration_seconds = time.monotonic() - started
            return result

        try:
            if not current.screenshot.available or current.screenshot.is_blank:
                result.fresh = False
                result.reason = "fresh_observation_unusable"
                return result

            result.app_changed = self._app_identity(planned) != self._app_identity(current)
            panel_before = planned.system_panel_visible
            panel_after = current.system_panel_visible
            result.system_panel_changed = bool(
                panel_before != panel_after
                and (
                    panel_before is True
                    or panel_after is True
                    or (panel_before is not None and panel_after is not None)
                )
            )
            result.dimensions_changed = self._display_size(planned) != self._display_size(current)
            if result.app_changed:
                result.fresh = False
                result.reason = "foreground_application_changed"
                return result
            if result.system_panel_changed:
                result.fresh = False
                result.reason = "system_panel_state_changed"
                return result
            if result.dimensions_changed:
                result.fresh = False
                result.reason = "display_dimensions_changed"
                return result

            if (
                planned.screenshot.sha256
                and planned.screenshot.sha256 == current.screenshot.sha256
            ):
                result.reason = "screenshots_identical"
                result.global_mean_difference = 0.0
                result.global_changed_pixel_ratio = 0.0
                result.target_mean_difference = 0.0
                result.target_changed_pixel_ratio = 0.0
                result.target_regions = len(self._target_points(action))
                return result

            planned_image, current_image = self._normalized_images(planned, current)
            global_before = self._crop_system_chrome(planned_image)
            global_after = self._crop_system_chrome(current_image)
            (
                result.global_mean_difference,
                result.global_changed_pixel_ratio,
            ) = self._difference_metrics(global_before, global_after)

            target_metrics = [
                self._difference_metrics(
                    planned_image.crop(box),
                    current_image.crop(box),
                )
                for box in self._target_boxes(action, planned_image.size)
            ]
            result.target_regions = len(target_metrics)
            if target_metrics:
                result.target_mean_difference = max(item[0] for item in target_metrics)
                result.target_changed_pixel_ratio = max(item[1] for item in target_metrics)

            target_stale = bool(
                result.target_mean_difference is not None
                and result.target_changed_pixel_ratio is not None
                and (
                    result.target_mean_difference
                    >= self.config.target_mean_difference_threshold
                    or result.target_changed_pixel_ratio
                    >= self.config.target_changed_pixel_ratio_threshold
                )
            )
            global_stale = bool(
                result.global_mean_difference is not None
                and result.global_changed_pixel_ratio is not None
                and result.global_mean_difference
                >= self.config.global_mean_difference_threshold
                and result.global_changed_pixel_ratio
                >= self.config.global_changed_pixel_ratio_threshold
            )
            if target_stale:
                result.fresh = False
                result.reason = "target_region_changed"
            elif global_stale:
                result.fresh = False
                result.reason = "broad_screen_change_detected"
            else:
                result.reason = "visual_precondition_compatible"
            return result
        except Exception as exc:
            result.fresh = False
            result.reason = "freshness_comparison_failed"
            result.comparison_error = f"{type(exc).__name__}: {exc}"
            return result
        finally:
            result.check_duration_seconds = time.monotonic() - started

    @staticmethod
    def _capture_age(observation: ScreenObservation) -> float | None:
        captured_at = float(observation.screenshot.timestamp or 0)
        if captured_at <= 0:
            return None
        return max(0.0, time.time() - captured_at)

    @staticmethod
    def _app_identity(observation: ScreenObservation) -> str:
        return str(observation.current_package or observation.current_app or "").strip().casefold()

    @staticmethod
    def _display_size(observation: ScreenObservation) -> tuple[int, int]:
        screenshot = observation.screenshot
        return (
            int(screenshot.display_width or screenshot.width),
            int(screenshot.display_height or screenshot.height),
        )

    def _normalized_images(
        self,
        planned: ScreenObservation,
        current: ScreenObservation,
    ) -> tuple[Image.Image, Image.Image]:
        before = self._decode_image(planned.screenshot.base64_data).convert("RGB")
        after = self._decode_image(current.screenshot.base64_data).convert("RGB")
        before_ratio = before.width / max(before.height, 1)
        after_ratio = after.width / max(after.height, 1)
        if abs(before_ratio - after_ratio) > 0.01:
            raise ValueError(
                f"Screenshot aspect ratio changed: {before.size} -> {after.size}"
            )
        width = self.config.image_compare_width
        height = max(1, round(width / before_ratio))
        size = (width, height)
        return (
            before.resize(size, Image.Resampling.BILINEAR),
            after.resize(size, Image.Resampling.BILINEAR),
        )

    def _difference_metrics(
        self,
        before: Image.Image,
        after: Image.Image,
    ) -> tuple[float, float]:
        difference = ImageChops.difference(before, after).convert("RGB")
        mean_channels = ImageStat.Stat(difference).mean
        mean_difference = sum(mean_channels) / (len(mean_channels) * 255.0)
        red, green, blue = difference.split()
        peak = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        cutoff = max(1, round(self.config.pixel_delta_threshold * 255))
        changed = peak.point(lambda value: 255 if value >= cutoff else 0)
        changed_pixel_ratio = ImageStat.Stat(changed).mean[0] / 255.0
        return (
            max(0.0, min(1.0, float(mean_difference))),
            max(0.0, min(1.0, float(changed_pixel_ratio))),
        )

    def _crop_system_chrome(self, image: Image.Image) -> Image.Image:
        top = round(image.height * self.config.crop_top_ratio)
        bottom = image.height - round(image.height * self.config.crop_bottom_ratio)
        return image if bottom <= top else image.crop((0, top, image.width, bottom))

    def _target_boxes(
        self,
        action: dict[str, Any],
        size: tuple[int, int],
    ) -> list[tuple[int, int, int, int]]:
        width, height = size
        radius_x = max(2, round(width * self.config.target_radius_x_ratio))
        radius_y = max(2, round(height * self.config.target_radius_y_ratio))
        boxes: list[tuple[int, int, int, int]] = []
        for x_relative, y_relative in self._target_points(action):
            x = round(float(x_relative) / 999 * (width - 1))
            y = round(float(y_relative) / 999 * (height - 1))
            boxes.append(
                (
                    max(0, x - radius_x),
                    max(0, y - radius_y),
                    min(width, x + radius_x + 1),
                    min(height, y + radius_y + 1),
                )
            )
        return boxes

    @staticmethod
    def _target_points(action: dict[str, Any]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        for field in ("element", "start", "end"):
            value = action.get(field)
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                continue
            x, y = value
            if all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in (x, y)
            ):
                points.append((float(x), float(y)))
        if action.get("action") == "Swipe" and len(points) == 2:
            points.append(
                (
                    (points[0][0] + points[1][0]) / 2,
                    (points[0][1] + points[1][1]) / 2,
                )
            )
        return points

    @staticmethod
    def _decode_image(encoded: str) -> Image.Image:
        image = Image.open(BytesIO(base64.b64decode(encoded)))
        image.load()
        return image
