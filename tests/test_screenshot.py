from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

import phoneagent.adb.screenshot as screenshot_module
from phoneagent.adb.command import ADBCommandError
from phoneagent.adb.screenshot import (
    ScreenshotCaptureError,
    ScreenshotDecodeError,
    ScreenshotPermissionError,
    ScreenshotTimeoutError,
    get_screenshot,
)


def adb_result(*, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def png_bytes(width: int = 80, height: int = 160, value: int = 80) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), (value, value, value)).save(output, format="PNG")
    return output.getvalue()


def test_invalid_screenshot_header_is_rejected_without_model_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screenshot_module,
        "run_adb",
        lambda *args, **kwargs: adb_result(stdout=b"not a png"),
    )

    with pytest.raises(ScreenshotDecodeError, match="Unexpected screenshot stream header"):
        get_screenshot(retries=0)


def test_secure_screen_marker_has_a_distinct_permission_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screenshot_module,
        "run_adb",
        lambda *args, **kwargs: adb_result(
            stdout=png_bytes(),
            stderr=b"capture blocked by secure flag",
        ),
    )

    with pytest.raises(ScreenshotPermissionError, match="Secure screen detected"):
        get_screenshot(retries=0)


def test_diagnostic_fallback_is_explicitly_unavailable_and_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def capture(*args, **kwargs):
        nonlocal calls
        calls += 1
        return adb_result(stdout=b"", stderr=b"device offline", returncode=1)

    monkeypatch.setattr(screenshot_module, "run_adb", capture)
    monkeypatch.setattr(screenshot_module, "_get_device_resolution", lambda device_id: (100, 200))
    monkeypatch.setattr(screenshot_module.time, "sleep", lambda seconds: None)

    fallback = get_screenshot(allow_fallback=True, retries=1, max_size=100)

    assert calls == 2
    assert fallback.available is False
    assert fallback.is_blank is True
    assert fallback.display_width == 100
    assert fallback.display_height == 200
    assert "Android rejected screenshot capture" in str(fallback.error)


def test_valid_screenshot_retains_display_size_when_model_image_is_resized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        screenshot_module,
        "run_adb",
        lambda *args, **kwargs: adb_result(stdout=png_bytes(width=100, height=200)),
    )

    screenshot = get_screenshot(retries=0, max_size=50, image_format="jpeg")

    assert screenshot.available is True
    assert screenshot.mime_type == "image/jpeg"
    assert (screenshot.display_width, screenshot.display_height) == (100, 200)
    assert (screenshot.width, screenshot.height) == (25, 50)
    assert screenshot.is_blank is False


def test_capture_parameter_validation_fails_before_adb() -> None:
    with pytest.raises(ValueError, match="max_size"):
        get_screenshot(max_size=0)
    with pytest.raises(ValueError, match="quality"):
        get_screenshot(quality=101)
    with pytest.raises(ValueError, match="retries"):
        get_screenshot(retries=-1)


@pytest.mark.parametrize(
    ("reason", "error_type"),
    [
        ("timed out after 1s", ScreenshotTimeoutError),
        ("adb executable not found", ScreenshotCaptureError),
    ],
)
def test_adb_transport_failures_keep_meaningful_screenshot_types(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    error_type: type[Exception],
) -> None:
    def fail(*args, **kwargs):
        raise ADBCommandError(["adb", "exec-out"], reason=reason)

    monkeypatch.setattr(screenshot_module, "run_adb", fail)

    with pytest.raises(error_type):
        get_screenshot(retries=0)
