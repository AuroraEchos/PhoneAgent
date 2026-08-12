from __future__ import annotations

import base64
import time
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from phoneagent.adb.screenshot import Screenshot
from phoneagent.devices import ScreenObservation
from phoneagent.runtime import (
    FreshnessConfig,
    ObservationFreshnessGuard,
)


def _observation(
    *,
    patches: list[tuple[tuple[int, int, int, int], tuple[int, int, int]]] | None = None,
    package: str = "com.example",
    timestamp: float | None = None,
) -> ScreenObservation:
    image = Image.new("RGB", (200, 400), (72, 72, 72))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((70, 180, 130, 220), radius=8, fill=(180, 180, 180))
    for box, color in patches or []:
        draw.rectangle(box, fill=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    screenshot = Screenshot(
        base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"),
        width=image.width,
        height=image.height,
        display_width=image.width,
        display_height=image.height,
        timestamp=time.time() if timestamp is None else timestamp,
        is_blank=False,
    )
    return ScreenObservation(
        screenshot=screenshot,
        current_app="Example",
        current_package=package,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("image_compare_width", 32),
        ("observation_retries", -1),
        ("observation_retry_delay", -0.1),
        ("target_radius_x_ratio", 0),
        ("target_radius_y_ratio", -0.1),
        ("pixel_delta_threshold", 0),
        ("target_mean_difference_threshold", 1.1),
        ("global_changed_pixel_ratio_threshold", -0.1),
    ],
)
def test_freshness_config_rejects_invalid_ranges(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        FreshnessConfig(**{field: value})


def test_identical_screen_authorizes_coordinate_action() -> None:
    guard = ObservationFreshnessGuard()
    planned = _observation(timestamp=time.time() - 3)
    current = _observation()

    result = guard.check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=planned,
        current=current,
    )

    assert result.checked is True
    assert result.fresh is True
    assert result.reason == "screenshots_identical"
    assert result.planned_capture_age_seconds is not None
    assert result.planned_capture_age_seconds >= 3


def test_change_covering_target_invalidates_action() -> None:
    guard = ObservationFreshnessGuard()
    planned = _observation()
    current = _observation(patches=[((55, 155, 145, 245), (15, 15, 15))])

    result = guard.check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=planned,
        current=current,
    )

    assert result.fresh is False
    assert result.reason == "target_region_changed"
    assert result.target_changed_pixel_ratio is not None
    assert result.target_changed_pixel_ratio >= 0.15


def test_small_unrelated_animation_does_not_invalidate_target() -> None:
    guard = ObservationFreshnessGuard()
    planned = _observation()
    current = _observation(patches=[((0, 40, 25, 70), (220, 220, 220))])

    result = guard.check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=planned,
        current=current,
    )

    assert result.fresh is True
    assert result.reason == "visual_precondition_compatible"
    assert result.target_changed_pixel_ratio == 0.0


def test_near_full_screen_replacement_invalidates_even_when_target_patch_is_preserved() -> None:
    planned = _observation()
    # Preserve the target neighborhood while changing most of the screen.
    current = _observation(
        patches=[
            ((0, 0, 199, 159), (25, 25, 25)),
            ((0, 241, 199, 399), (25, 25, 25)),
            ((0, 160, 54, 240), (25, 25, 25)),
            ((146, 160, 199, 240), (25, 25, 25)),
        ]
    )

    result = ObservationFreshnessGuard().check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=planned,
        current=current,
    )

    assert result.fresh is False
    assert result.reason == "broad_screen_change_detected"


def test_dynamic_feed_change_does_not_override_unchanged_target() -> None:
    planned = _observation()
    # A large content/card region changes, but the selected control remains
    # pixel-identical. This resembles a carousel or video frame update.
    current = _observation(patches=[((0, 20, 199, 150), (25, 25, 25))])

    result = ObservationFreshnessGuard().check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=planned,
        current=current,
    )

    assert result.global_changed_pixel_ratio is not None
    assert result.global_changed_pixel_ratio >= 0.30
    assert result.target_changed_pixel_ratio == 0.0
    assert result.fresh is True
    assert result.reason == "visual_precondition_compatible"


def test_foreground_package_change_invalidates_before_image_comparison() -> None:
    result = ObservationFreshnessGuard().check(
        action={"_metadata": "do", "action": "Tap", "element": [500, 500]},
        planned=_observation(package="com.example"),
        current=_observation(package="com.overlay"),
    )

    assert result.fresh is False
    assert result.reason == "foreground_application_changed"
    assert result.app_changed is True


def test_non_coordinate_action_does_not_require_freshness_check() -> None:
    guard = ObservationFreshnessGuard()
    assert guard.requires_check({"_metadata": "do", "action": "Launch"}) is False
    assert guard.requires_check({"_metadata": "finish"}) is False
