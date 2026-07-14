from __future__ import annotations

from phoneagent.actions import ActionResult, do
from phoneagent.runtime import ActionVerifier, VerificationConfig, VerificationStatus

from conftest import make_observation


def test_tap_only_verifies_observable_change() -> None:
    verifier = ActionVerifier(VerificationConfig(visual_change_threshold=0.001))
    result = verifier.verify(
        action=do(action="Tap", element=[500, 500]),
        execution=ActionResult(True, False),
        before=make_observation(10, app="Example", package="com.example"),
        after=make_observation(80, app="Example", package="com.example"),
    )
    assert result.status is VerificationStatus.PASSED
    assert result.observable_effect_verified is True
    assert result.semantic_effect_verified is None


def test_direct_launch_verifies_semantic_app_effect() -> None:
    verifier = ActionVerifier()
    result = verifier.verify(
        action=do(action="Launch", app="com.tencent.mm"),
        execution=ActionResult(
            True,
            False,
            metadata={"package_name": "com.tencent.mm"},
        ),
        before=make_observation(10, app="System Home", package="com.android.launcher"),
        after=make_observation(10, app="WeChat", package="com.tencent.mm"),
    )
    assert result.status is VerificationStatus.PASSED
    assert result.semantic_effect_verified is True


def test_launcher_search_requires_observed_change() -> None:
    verifier = ActionVerifier()
    before = make_observation(10, app="System Home", package="com.android.launcher")
    result = verifier.verify(
        action=do(action="Launch", app="Unknown App"),
        execution=ActionResult(
            True,
            False,
            metadata={"visual_completion_required": True},
        ),
        before=before,
        after=before,
    )
    assert result.status is VerificationStatus.FAILED
    assert result.error_code == "launcher_search_not_observed"
    assert result.observable_effect_verified is False
    assert result.semantic_effect_verified is False


def test_launcher_search_change_is_not_claimed_as_launch_success() -> None:
    verifier = ActionVerifier(VerificationConfig(visual_change_threshold=0.001))
    result = verifier.verify(
        action=do(action="Launch", app="Unknown App"),
        execution=ActionResult(
            True,
            False,
            metadata={"visual_completion_required": True},
        ),
        before=make_observation(10, app="System Home", package="com.android.launcher"),
        after=make_observation(80, app="System Home", package="com.android.launcher"),
    )
    assert result.status is VerificationStatus.PASSED
    assert result.observable_effect_verified is True
    assert result.semantic_effect_verified is False


def test_disabled_verification_does_not_claim_effect() -> None:
    verifier = ActionVerifier(VerificationConfig(enabled=False))
    result = verifier.verify(
        action=do(action="Tap", element=[500, 500]),
        execution=ActionResult(True, False),
        before=make_observation(10),
        after=None,
    )
    assert result.status is VerificationStatus.SKIPPED
    assert result.observable_effect_verified is None
    assert result.semantic_effect_verified is None


def test_status_bar_only_change_is_ignored() -> None:
    import base64
    from io import BytesIO

    from PIL import Image, ImageDraw

    from phoneagent.adb.screenshot import Screenshot
    from phoneagent.devices import ScreenObservation

    def observation(top_value: int) -> ScreenObservation:
        image = Image.new("RGB", (100, 200), (80, 80, 80))
        ImageDraw.Draw(image).rectangle((0, 0, 99, 5), fill=(top_value,) * 3)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        screenshot = Screenshot(
            base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"),
            width=100,
            height=200,
            display_width=100,
            display_height=200,
            is_blank=False,
        )
        return ScreenObservation(
            screenshot=screenshot,
            current_app="Example",
            current_package="com.example",
        )

    verifier = ActionVerifier(
        VerificationConfig(
            visual_change_threshold=0.001,
            crop_top_ratio=0.04,
            crop_bottom_ratio=0,
        )
    )
    result = verifier.verify(
        action=do(action="Tap", element=[500, 500]),
        execution=ActionResult(True, False),
        before=observation(0),
        after=observation(255),
    )
    assert result.status is VerificationStatus.FAILED
    assert result.visual_difference_ratio == 0.0


def test_wait_has_deterministic_action_semantics_without_claiming_visual_change() -> None:
    verifier = ActionVerifier()
    result = verifier.verify(
        action=do(action="Wait", duration="1 second"),
        execution=ActionResult(True, False, metadata={"waited_seconds": 1.0}),
        before=make_observation(10),
        after=make_observation(10),
    )
    assert result.status is VerificationStatus.PASSED
    assert result.observable_effect_verified is None
    assert result.semantic_effect_verified is True
