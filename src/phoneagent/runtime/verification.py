"""Post-action verification for Android GUI actions.

The verifier deliberately distinguishes three different facts:

``command_success``
    The Android/ADB command was accepted by the execution layer.
``observable_effect_verified``
    A deterministic system-state or visual effect was observed afterwards.
``semantic_effect_verified``
    The observed state proves the requested action-level semantic outcome.

For most coordinate-based GUI actions PhoneAgent can only verify an observable
change. It cannot prove that the model clicked the semantically correct target.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from typing import Any

from PIL import Image, ImageChops, ImageStat

from phoneagent.actions import ActionResult
from phoneagent.config.apps import get_package_name
from phoneagent.devices import ScreenObservation


class VerificationStatus(str, Enum):
    """Outcome of one verification policy."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


@dataclass(slots=True)
class VerificationConfig:
    """Runtime knobs for deterministic post-action verification."""

    enabled: bool = True
    settle_delay_seconds: float = 0.15
    observation_retries: int = 1
    observation_retry_delay: float = 0.35
    visual_change_threshold: float = 0.002
    image_compare_size: int = 128
    crop_top_ratio: float = 0.04
    crop_bottom_ratio: float = 0.04

    def __post_init__(self) -> None:
        if self.settle_delay_seconds < 0:
            raise ValueError("verification settle_delay_seconds cannot be negative")
        if self.observation_retries < 0:
            raise ValueError("verification observation_retries cannot be negative")
        if self.observation_retry_delay < 0:
            raise ValueError("verification observation_retry_delay cannot be negative")
        if not 0 <= self.visual_change_threshold <= 1:
            raise ValueError("visual_change_threshold must be in the 0..1 range")
        if self.image_compare_size < 16:
            raise ValueError("image_compare_size must be at least 16")
        for name in ("crop_top_ratio", "crop_bottom_ratio"):
            value = float(getattr(self, name))
            if not 0 <= value < 0.5:
                raise ValueError(f"{name} must be in the range [0, 0.5)")
        if self.crop_top_ratio + self.crop_bottom_ratio >= 0.8:
            raise ValueError("verification crop ratios leave too little image content")


@dataclass(slots=True)
class VerificationResult:
    """Structured evidence collected after an action."""

    status: VerificationStatus
    policy: str
    message: str
    command_success: bool
    observable_effect_verified: bool | None
    semantic_effect_verified: bool | None = None
    screen_changed: bool | None = None
    app_changed: bool | None = None
    visual_difference_ratio: float | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether the runtime may continue without recovery."""
        return self.status in {VerificationStatus.PASSED, VerificationStatus.SKIPPED}

    @property
    def verification_enabled(self) -> bool:
        return self.policy != "verification_disabled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "policy": self.policy,
            "message": self.message,
            "command_success": self.command_success,
            "observable_effect_verified": self.observable_effect_verified,
            "semantic_effect_verified": self.semantic_effect_verified,
            "screen_changed": self.screen_changed,
            "app_changed": self.app_changed,
            "visual_difference_ratio": self.visual_difference_ratio,
            "error_code": self.error_code,
            "metadata": dict(self.metadata),
        }


class ActionVerifier:
    """Apply action-specific verification rules to before/after observations."""

    _NO_SCREEN_EFFECT_ACTIONS = {"Note", "Call_API"}
    _OBSERVATION_ONLY_ACTIONS = {"Take_over", "Interact"}
    _SCREEN_CHANGE_ACTIONS = {
        "Tap",
        "Double Tap",
        "Long Press",
        "Swipe",
        "Type",
        "Back",
    }

    def __init__(self, config: VerificationConfig | None = None):
        self.config = config or VerificationConfig()

    def verify(
        self,
        *,
        action: dict[str, Any],
        execution: ActionResult,
        before: ScreenObservation,
        after: ScreenObservation | None,
    ) -> VerificationResult:
        if not execution.success:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                policy="command_success",
                message=execution.message or "Action command failed",
                command_success=False,
                observable_effect_verified=False,
                semantic_effect_verified=False,
                error_code=execution.error_code or "action_command_failed",
                metadata={"execution_metadata": dict(execution.metadata)},
            )

        if action.get("_metadata") == "finish":
            return VerificationResult(
                status=VerificationStatus.SKIPPED,
                policy="finish_action",
                message="Finish actions do not mutate the device",
                command_success=True,
                observable_effect_verified=None,
                semantic_effect_verified=None,
            )

        action_name = str(action.get("action", ""))
        if not self.config.enabled:
            return VerificationResult(
                status=VerificationStatus.SKIPPED,
                policy="verification_disabled",
                message="Post-action verification is disabled",
                command_success=True,
                observable_effect_verified=None,
                semantic_effect_verified=None,
            )

        if action_name in self._NO_SCREEN_EFFECT_ACTIONS:
            return VerificationResult(
                status=VerificationStatus.PASSED,
                policy="command_only",
                message=f"{action_name} completed; no device-screen effect is required",
                command_success=True,
                observable_effect_verified=None,
                semantic_effect_verified=True,
            )

        if after is None or not after.screenshot.available:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                policy="post_observation",
                message="Action executed but the post-action screen could not be observed",
                command_success=True,
                observable_effect_verified=False,
                semantic_effect_verified=False,
                error_code="verification_observation_failed",
            )

        difference = self._visual_difference_ratio(before, after)
        app_changed = bool(
            before.current_package != after.current_package
            or before.current_app != after.current_app
        )
        screen_changed = bool(
            app_changed
            or (
                difference is not None
                and difference >= self.config.visual_change_threshold
            )
        )
        common_metadata = {
            "before_app": before.current_app,
            "after_app": after.current_app,
            "before_package": before.current_package,
            "after_package": after.current_package,
            "before_sha256": before.screenshot.sha256,
            "after_sha256": after.screenshot.sha256,
            "threshold": self.config.visual_change_threshold,
            "crop_top_ratio": self.config.crop_top_ratio,
            "crop_bottom_ratio": self.config.crop_bottom_ratio,
            "execution_metadata": dict(execution.metadata),
        }
        common = {
            "screen_changed": screen_changed,
            "app_changed": app_changed,
            "visual_difference_ratio": difference,
            "metadata": common_metadata,
        }

        if action_name == "Launch":
            if execution.metadata.get("visual_completion_required") is True:
                common_metadata["visual_completion_required"] = True
                if screen_changed:
                    return VerificationResult(
                        status=VerificationStatus.PASSED,
                        policy="launcher_search_observed",
                        message=(
                            "A Launcher-search state change was observed. The requested "
                            "application has not been semantically verified as launched; "
                            "the model must inspect and select the correct result."
                        ),
                        command_success=True,
                        observable_effect_verified=True,
                        semantic_effect_verified=False,
                        **common,
                    )
                return VerificationResult(
                    status=VerificationStatus.FAILED,
                    policy="launcher_search_observed",
                    message=(
                        "Launcher search fallback reported success, but no foreground or "
                        "visual change was observed"
                    ),
                    command_success=True,
                    observable_effect_verified=False,
                    semantic_effect_verified=False,
                    error_code="launcher_search_not_observed",
                    **common,
                )

            expected_app = str(
                execution.metadata.get("package_name") or action.get("app", "")
            )
            actual_app = after.current_package or after.current_app
            if self._same_app(expected_app, actual_app):
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    policy="foreground_app_match",
                    message=f"Foreground application matches {expected_app}",
                    command_success=True,
                    observable_effect_verified=True,
                    semantic_effect_verified=True,
                    **common,
                )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                policy="foreground_app_match",
                message=(
                    f"Launch command completed but foreground app is {after.current_app!r}, "
                    f"expected {expected_app!r}"
                ),
                command_success=True,
                observable_effect_verified=False,
                semantic_effect_verified=False,
                error_code="verification_app_mismatch",
                **common,
            )

        if action_name == "Home":
            if after.current_app == "System Home":
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    policy="system_home",
                    message="System Home is now foreground",
                    command_success=True,
                    observable_effect_verified=True,
                    semantic_effect_verified=True,
                    **common,
                )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                policy="system_home",
                message=f"Home command did not reach System Home: {after.current_app}",
                command_success=True,
                observable_effect_verified=False,
                semantic_effect_verified=False,
                error_code="verification_home_failed",
                **common,
            )

        if action_name == "Wait":
            return VerificationResult(
                status=VerificationStatus.PASSED,
                policy="timed_wait_completed",
                message="The bounded wait completed and a trusted observation is available",
                command_success=True,
                observable_effect_verified=None,
                semantic_effect_verified=True,
                **common,
            )

        if action_name in {"Take_over", "Interact"}:
            return VerificationResult(
                status=VerificationStatus.PASSED,
                policy="post_observation_available",
                message="A trusted post-interaction observation is available",
                command_success=True,
                observable_effect_verified=None,
                semantic_effect_verified=None,
                **common,
            )

        if action_name in self._SCREEN_CHANGE_ACTIONS:
            if screen_changed:
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    policy="observable_screen_change",
                    message=(
                        "A foreground or visual change was detected. This verifies an "
                        "observable effect, not semantic target correctness."
                    ),
                    command_success=True,
                    observable_effect_verified=True,
                    semantic_effect_verified=None,
                    **common,
                )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                policy="observable_screen_change",
                message=(
                    f"{action_name} command completed but no meaningful observable change "
                    "was detected"
                ),
                command_success=True,
                observable_effect_verified=False,
                semantic_effect_verified=None,
                error_code="verification_no_effect",
                **common,
            )

        return VerificationResult(
            status=VerificationStatus.INCONCLUSIVE,
            policy="verification_policy_missing",
            message=f"No verification policy is defined for action {action_name!r}",
            command_success=True,
            observable_effect_verified=None,
            semantic_effect_verified=None,
            error_code="verification_inconclusive",
            **common,
        )

    def observation_failure(
        self,
        *,
        action: dict[str, Any],
        execution: ActionResult,
        message: str,
        error_code: str = "verification_observation_failed",
    ) -> VerificationResult:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            policy="post_observation",
            message=message,
            command_success=execution.success,
            observable_effect_verified=False,
            semantic_effect_verified=False,
            error_code=error_code,
            metadata={"action": dict(action)},
        )

    def _visual_difference_ratio(
        self, before: ScreenObservation, after: ScreenObservation
    ) -> float | None:
        if before.screenshot.sha256 and before.screenshot.sha256 == after.screenshot.sha256:
            return 0.0
        try:
            before_image = self._decode_image(before.screenshot.base64_data).convert("L")
            after_image = self._decode_image(after.screenshot.base64_data).convert("L")
            before_image = self._crop_system_chrome(before_image)
            after_image = self._crop_system_chrome(after_image)
            size = (self.config.image_compare_size, self.config.image_compare_size)
            before_image = before_image.resize(size)
            after_image = after_image.resize(size)
            difference = ImageChops.difference(before_image, after_image)
            mean = ImageStat.Stat(difference).mean[0]
            return max(0.0, min(1.0, float(mean) / 255.0))
        except Exception:
            if before.screenshot.sha256 and after.screenshot.sha256:
                return 1.0 if before.screenshot.sha256 != after.screenshot.sha256 else 0.0
            return None


    def _crop_system_chrome(self, image: Image.Image) -> Image.Image:
        """Ignore small top/bottom bands that commonly contain clocks/navigation bars."""
        width, height = image.size
        top = round(height * self.config.crop_top_ratio)
        bottom = height - round(height * self.config.crop_bottom_ratio)
        if bottom <= top:
            return image
        return image.crop((0, top, width, bottom))

    @staticmethod
    def _decode_image(encoded: str) -> Image.Image:
        image = Image.open(BytesIO(base64.b64decode(encoded)))
        image.load()
        return image

    @staticmethod
    def _same_app(expected: str, actual: str) -> bool:
        expected_package = get_package_name(expected) or expected.strip()
        actual_package = get_package_name(actual)
        if actual.startswith("Unknown (") and actual.endswith(")"):
            actual_package = actual[len("Unknown (") : -1]
        actual_package = actual_package or actual.strip()
        if expected_package and actual_package:
            return expected_package == actual_package
        return expected.strip().casefold() == actual.strip().casefold()
