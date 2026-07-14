"""Screenshot utilities for capturing Android device screens."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageStat, UnidentifiedImageError

from phoneagent.adb.command import ADBCommandError, run_adb

logger = logging.getLogger(__name__)


class ScreenshotCaptureError(RuntimeError):
    """Raised when a trustworthy screen observation cannot be captured."""


@dataclass(slots=True)
class Screenshot:
    """A captured and model-ready screenshot.

    ``width`` / ``height`` describe the encoded image sent to the model.
    ``display_width`` / ``display_height`` describe the Android coordinate space.
    """

    base64_data: str
    width: int
    height: int
    mime_type: str = "image/png"
    display_width: int | None = None
    display_height: int | None = None
    is_sensitive: bool = False
    timestamp: float = 0.0
    available: bool = True
    error: str | None = None
    sha256: str = ""
    is_blank: bool = False

    def __post_init__(self) -> None:
        if self.display_width is None:
            self.display_width = self.width
        if self.display_height is None:
            self.display_height = self.height
        if not self.sha256 and self.base64_data:
            try:
                self.sha256 = hashlib.sha256(
                    base64.b64decode(self.base64_data)
                ).hexdigest()
            except Exception:
                self.sha256 = ""


def get_screenshot(
    device_id: str | None = None,
    timeout: int = 10,
    max_size: int = 1280,
    image_format: str = "JPEG",
    quality: int = 90,
    *,
    allow_fallback: bool = False,
) -> Screenshot:
    """Capture a screen image from Android.

    By default a capture failure raises :class:`ScreenshotCaptureError` rather
    than silently sending a synthetic black image to the model. Set
    ``allow_fallback=True`` only for diagnostics or UI code that can explicitly
    handle ``Screenshot.available == False``.
    """
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if not 1 <= int(quality) <= 100:
        raise ValueError("quality must be in the range 1..100")

    image_format = _normalize_image_format(image_format)
    mime_type = _mime_type_for_format(image_format)

    try:
        result = run_adb(
            ["exec-out", "screencap", "-p"],
            device_id=device_id,
            timeout=timeout,
            check=False,
            text=False,
            retries=1,
        )
        stdout = _as_bytes(result.stdout)
        stderr = _as_bytes(result.stderr)
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if result.returncode != 0:
            stdout_text = stdout[:512].decode("utf-8", errors="replace").strip()
            diagnostic = "\n".join(part for part in (stderr_text, stdout_text) if part)
            raise ScreenshotCaptureError(
                "Android rejected screenshot capture"
                + (f": {diagnostic[:500]}" if diagnostic else "")
            )
        if not stdout:
            raise ScreenshotCaptureError(
                "Empty screenshot data received"
                + (f": {stderr_text[:500]}" if stderr_text else "")
            )
        if not stdout.startswith(b"\x89PNG"):
            stdout_text = stdout[:512].decode("utf-8", errors="replace").strip()
            diagnostic = "\n".join(part for part in (stderr_text, stdout_text) if part)
            raise ScreenshotCaptureError(
                f"Unexpected screenshot stream header: {stdout[:16]!r}"
                + (f"; diagnostic: {diagnostic[:500]}" if diagnostic else "")
            )

        # Never scan compressed PNG bytes for text markers. Only stderr is
        # textual and trustworthy at this point; a binary PNG can contain any
        # byte sequence by coincidence.
        failure_markers = (
            "status: -1",
            "failed",
            "permission denied",
            "secure flag",
            "unable to capture",
        )
        if any(marker in stderr_text.casefold() for marker in failure_markers):
            raise ScreenshotCaptureError(
                f"Android reported an untrustworthy screenshot: {stderr_text[:500]}"
            )

        try:
            image = Image.open(BytesIO(stdout))
            image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ScreenshotCaptureError(f"Invalid screenshot image: {exc}") from exc

        display_width, display_height = image.size
        if display_width <= 0 or display_height <= 0:
            raise ScreenshotCaptureError(
                f"Invalid screenshot dimensions: {display_width}x{display_height}"
            )

        image = _resize_image(image, max_size=max_size)
        is_blank = _is_nearly_uniform_black(image)
        encoded_bytes = _encode_image(image, image_format, quality)
        encoded = base64.b64encode(encoded_bytes).decode("utf-8")
        width, height = image.size

        return Screenshot(
            base64_data=encoded,
            width=width,
            height=height,
            mime_type=mime_type,
            display_width=display_width,
            display_height=display_height,
            is_sensitive=is_blank,
            timestamp=time.time(),
            available=True,
            error=None,
            sha256=hashlib.sha256(encoded_bytes).hexdigest(),
            is_blank=is_blank,
        )
    except (ADBCommandError, ScreenshotCaptureError, OSError, ValueError) as exc:
        logger.warning("Screenshot capture failed: %s", exc)
        if not allow_fallback:
            if isinstance(exc, ScreenshotCaptureError):
                raise
            raise ScreenshotCaptureError(str(exc)) from exc
        return _create_fallback_screenshot(
            device_id=device_id,
            is_sensitive=isinstance(exc, ScreenshotCaptureError),
            max_size=max_size,
            image_format=image_format,
            quality=quality,
            error=str(exc),
        )


def _as_bytes(value: str | bytes | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def _normalize_image_format(image_format: str) -> str:
    normalized = (image_format or "PNG").strip().upper()
    aliases = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}
    return aliases.get(normalized, "PNG")


def _mime_type_for_format(image_format: str) -> str:
    normalized = _normalize_image_format(image_format)
    if normalized == "JPEG":
        return "image/jpeg"
    if normalized == "WEBP":
        return "image/webp"
    return "image/png"


def _resize_image(image: Image.Image, max_size: int) -> Image.Image:
    width, height = image.size
    long_side = max(width, height)
    if long_side <= max_size:
        return image.copy()
    scale = max_size / long_side
    new_size = (
        max(1, round(width * scale)),
        max(1, round(height * scale)),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_image(image: Image.Image, image_format: str, quality: int) -> bytes:
    buffered = BytesIO()
    save_kwargs: dict[str, int | bool] = {}
    if image_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        save_kwargs.update(quality=int(quality), optimize=True)
    image.save(buffered, format=image_format, **save_kwargs)
    return buffered.getvalue()


def _is_nearly_uniform_black(image: Image.Image) -> bool:
    """Detect fully protected/blank captures without rejecting normal dark UIs."""
    sample = image.convert("L")
    sample.thumbnail((64, 64))
    stats = ImageStat.Stat(sample)
    mean = stats.mean[0]
    variance = stats.var[0]
    return mean < 2.0 and variance < 1.0


def _get_device_resolution(device_id: str | None = None) -> tuple[int, int]:
    try:
        result = run_adb(
            ["shell", "wm", "size"],
            device_id=device_id,
            timeout=5,
            check=False,
            text=True,
            retries=1,
        )
        output = (result.stdout or "") + (result.stderr or "")
        # Override size is the effective coordinate space when present.
        override = re.search(r"Override size:\s*(\d+)x(\d+)", output)
        physical = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        match = override or physical or re.search(r"(\d+)x(\d+)", output)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        logger.debug("Failed to query device resolution", exc_info=True)
    return 1080, 2400


def _create_fallback_screenshot(
    device_id: str | None = None,
    is_sensitive: bool = False,
    max_size: int = 1280,
    image_format: str = "JPEG",
    quality: int = 90,
    error: str | None = None,
) -> Screenshot:
    image_format = _normalize_image_format(image_format)
    width, height = _get_device_resolution(device_id)
    display_width, display_height = width, height
    image = Image.new("RGB", (width, height), color="black")
    image = _resize_image(image, max_size=max_size)
    encoded_bytes = _encode_image(image, image_format, quality)
    encoded = base64.b64encode(encoded_bytes).decode("utf-8")
    width, height = image.size
    return Screenshot(
        base64_data=encoded,
        width=width,
        height=height,
        mime_type=_mime_type_for_format(image_format),
        display_width=display_width,
        display_height=display_height,
        is_sensitive=is_sensitive,
        timestamp=time.time(),
        available=False,
        error=error or "Screenshot unavailable",
        sha256=hashlib.sha256(encoded_bytes).hexdigest(),
        is_blank=True,
    )
