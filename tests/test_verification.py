from __future__ import annotations

import pytest

from phoneagent.actions import ActionResult, do, finish
from phoneagent.runtime import ActionVerifier, VerificationConfig, VerificationStatus

from conftest import make_observation


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("settle_delay_seconds", -1),
        ("observation_retries", -1),
        ("observation_retry_delay", -1),
        ("visual_change_threshold", 1.1),
        ("image_compare_size", 8),
        ("crop_top_ratio", 0.5),
        ("crop_bottom_ratio", -0.1),
    ],
)
def test_verification_config_rejects_unsafe_ranges(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        VerificationConfig(**{field: value})


def test_verification_config_rejects_combined_overcropping() -> None:
    with pytest.raises(ValueError, match="too little image content"):
        VerificationConfig(crop_top_ratio=0.4, crop_bottom_ratio=0.4)


def test_failed_command_short_circuits_visual_verification() -> None:
    result = ActionVerifier().verify(
        action=do(action="Tap", element=[500, 500]),
        execution=ActionResult(
            False,
            False,
            message="ADB disconnected",
            error_code="action_execution_failed",
            metadata={"exception_type": "ConnectionError"},
        ),
        before=make_observation(10),
        after=make_observation(80),
    )

    assert result.status is VerificationStatus.FAILED
    assert result.policy == "command_success"
    assert result.error_code == "action_execution_failed"
    assert result.metadata["execution_metadata"]["exception_type"] == "ConnectionError"


def test_finish_and_command_only_actions_have_explicit_semantics() -> None:
    verifier = ActionVerifier()
    finished = verifier.verify(
        action=finish("done"),
        execution=ActionResult(True, True, "done"),
        before=make_observation(10),
        after=None,
    )
    note = verifier.verify(
        action=do(action="Note", message="remember"),
        execution=ActionResult(True, False),
        before=make_observation(10),
        after=None,
    )

    assert finished.status is VerificationStatus.SKIPPED
    assert finished.policy == "finish_action"
    assert note.status is VerificationStatus.PASSED
    assert note.semantic_effect_verified is True


def test_missing_post_action_observation_is_structured_failure() -> None:
    result = ActionVerifier().verify(
        action=do(action="Back"),
        execution=ActionResult(True, False),
        before=make_observation(10),
        after=None,
    )

    assert result.error_code == "verification_observation_failed"
    assert result.command_success is True


def test_home_and_unknown_actions_use_distinct_policies() -> None:
    verifier = ActionVerifier()
    before = make_observation(10, app="Example")
    home = verifier.verify(
        action=do(action="Home"),
        execution=ActionResult(True, False),
        before=before,
        after=make_observation(80, app="System Home"),
    )
    missed_home = verifier.verify(
        action=do(action="Home"),
        execution=ActionResult(True, False),
        before=before,
        after=make_observation(80, app="Settings"),
    )
    unknown = verifier.verify(
        action={"_metadata": "do", "action": "CustomAdapterAction"},
        execution=ActionResult(True, False),
        before=before,
        after=make_observation(80, app="Example"),
    )

    assert home.status is VerificationStatus.PASSED
    assert missed_home.error_code == "verification_home_failed"
    assert unknown.status is VerificationStatus.INCONCLUSIVE
    assert unknown.error_code == "verification_inconclusive"


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


def test_direct_launch_rejects_foreground_package_mismatch() -> None:
    verifier = ActionVerifier()
    result = verifier.verify(
        action=do(action="Launch", app="微信"),
        execution=ActionResult(
            True,
            False,
            metadata={"package_name": "com.tencent.mm"},
        ),
        before=make_observation(10, app="System Home", package="com.android.launcher"),
        after=make_observation(80, app="Settings", package="com.android.settings"),
    )
    assert result.status is VerificationStatus.FAILED
    assert result.error_code == "verification_app_mismatch"
    assert result.observable_effect_verified is False
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


def test_system_chrome_is_included_when_action_targets_it() -> None:
    import base64
    from io import BytesIO

    from PIL import Image, ImageDraw

    from phoneagent.adb.screenshot import Screenshot
    from phoneagent.devices import ScreenObservation

    def observation(top_value: int) -> ScreenObservation:
        image = Image.new("RGB", (100, 200), (80, 80, 80))
        ImageDraw.Draw(image).rectangle((0, 0, 99, 7), fill=(top_value,) * 3)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return ScreenObservation(
            screenshot=Screenshot(
                base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"),
                width=100,
                height=200,
                is_blank=False,
            ),
            current_app="Example",
            current_package="com.example",
        )

    verifier = ActionVerifier(VerificationConfig(visual_change_threshold=0.001))
    before = observation(0)
    after = observation(255)
    result = verifier.verify(
        action=do(action="Tap", element=[500, 10]),
        execution=ActionResult(True, False),
        before=before,
        after=after,
    )

    assert verifier.visual_signature(before) == verifier.visual_signature(after)
    assert result.status is VerificationStatus.PASSED
    assert result.metadata["comparison_region"] == "full_screen"


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


def test_open_system_panel_requires_visible_panel_state() -> None:
    verifier = ActionVerifier(VerificationConfig(visual_change_threshold=0.001))
    before = make_observation(10, app="Example", package="com.example")
    after = make_observation(80, app="Example", package="com.example")
    after.system_panel_visible = False

    result = verifier.verify(
        action=do(action="OpenQuickSettings"),
        execution=ActionResult(True, False),
        before=before,
        after=after,
    )

    assert result.status is VerificationStatus.FAILED
    assert result.error_code == "verification_system_panel_not_open"
    assert result.semantic_effect_verified is False


def test_open_system_panel_semantics_pass_when_overlay_is_visible() -> None:
    verifier = ActionVerifier()
    before = make_observation(10, app="Example", package="com.example")
    before.system_panel_visible = False
    after = make_observation(80, app="Unknown (com.android.systemui)", package="com.android.systemui")
    after.system_panel_visible = True
    after.system_panel_name = "notificationshade"

    result = verifier.verify(
        action=do(action="OpenNotifications"),
        execution=ActionResult(True, False),
        before=before,
        after=after,
    )

    assert result.status is VerificationStatus.PASSED
    assert result.semantic_effect_verified is True
    assert result.metadata["comparison_region"] == "full_screen"


def test_close_system_panel_is_idempotently_verified() -> None:
    verifier = ActionVerifier()
    before = make_observation(10)
    after = make_observation(10)
    before.system_panel_visible = False
    after.system_panel_visible = False

    result = verifier.verify(
        action=do(action="CloseSystemPanel"),
        execution=ActionResult(True, False),
        before=before,
        after=after,
    )

    assert result.status is VerificationStatus.PASSED
    assert result.observable_effect_verified is None
    assert result.semantic_effect_verified is True
