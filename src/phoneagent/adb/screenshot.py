"""Screenshot utilities for capturing Android device screens."""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Final

from PIL import Image, ImageStat, UnidentifiedImageError

from phoneagent.adb.command import ADBCommandError, run_adb

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class ScreenshotCaptureError(RuntimeError):
    """Raised when a trustworthy screen observation cannot be captured."""
    pass


class ScreenshotPermissionError(ScreenshotCaptureError):
    """Raised when screenshot is blocked by secure flag or permissions."""
    pass


class ScreenshotDecodeError(ScreenshotCaptureError):
    """Raised when screenshot data is corrupted or in unexpected format."""
    pass


class ScreenshotTimeoutError(ScreenshotCaptureError):
    """Raised when screenshot capture times out."""
    pass


# ============================================================================
# Constants
# ============================================================================

DEFAULT_SCREENSHOT_TIMEOUT: Final[int] = 10
DEFAULT_MAX_SIZE: Final[int] = 1280
DEFAULT_IMAGE_QUALITY: Final[int] = 90
DEFAULT_DEVICE_RESOLUTION: Final[tuple[int, int]] = (1080, 2400)

SUPPORTED_IMAGE_FORMATS: Final[dict[str, str]] = {
    "JPG": "JPEG",
    "JPEG": "JPEG",
    "PNG": "PNG",
    "WEBP": "WEBP",
}

MIME_TYPES: Final[dict[str, str]] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# Markers that indicate screenshot failure when present in stderr
FAILURE_MARKERS: Final[tuple[str, ...]] = (
    "status: -1",
    "failed",
    "permission denied",
    "secure flag",
    "unable to capture",
)


# ============================================================================
# Data Models
# ============================================================================

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
            except Exception as exc:  # pragma: no cover
                logger.debug("Failed to compute SHA256: %s", exc)
                self.sha256 = ""


# ============================================================================
# Public API
# ============================================================================

def get_screenshot(
    device_id: str | None = None,
    timeout: int | None = DEFAULT_SCREENSHOT_TIMEOUT,
    max_size: int = DEFAULT_MAX_SIZE,
    image_format: str = "PNG",
    quality: int = DEFAULT_IMAGE_QUALITY,
    *,
    allow_fallback: bool = False,
    retries: int = 1,
) -> Screenshot:
    """Capture a screen image from Android.

    By default a capture failure raises :class:`ScreenshotCaptureError` rather
    than silently sending a synthetic black image to the model. Set
    ``allow_fallback=True`` only for diagnostics or UI code that can explicitly
    handle ``Screenshot.available == False``.

    Args:
        device_id: Optional ADB device ID.
        timeout: Command timeout in seconds. None means no timeout.
        max_size: Maximum dimension for image resizing (preserves aspect ratio).
        image_format: Output format (PNG, JPEG, WEBP). Defaults to PNG.
        quality: JPEG/WEBP quality (1-100). Ignored for PNG.
        allow_fallback: Return placeholder screenshot on failure instead of raising.
        retries: Number of retry attempts on transient failures.

    Returns:
        Screenshot object containing the captured image and metadata.

    Raises:
        ScreenshotCaptureError: If screenshot fails and allow_fallback is False.
        ValueError: If parameters are invalid.
    """
    # Validate parameters
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if not 1 <= int(quality) <= 100:
        raise ValueError("quality must be in the range 1..100")
    if retries < 0:
        raise ValueError("retries must be non-negative")

    image_format = _normalize_image_format(image_format)
    mime_type = MIME_TYPES.get(image_format, "image/png")

    # Try to capture with retries
    last_exception: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if attempt > 0:
                logger.debug("Retrying screenshot capture (attempt %d/%d)", attempt, retries)
                # Brief backoff before retry
                time.sleep(0.5 * attempt)

            return _capture_screenshot_impl(
                device_id=device_id,
                timeout=timeout,
                max_size=max_size,
                image_format=image_format,
                mime_type=mime_type,
                quality=quality,
            )
        except ScreenshotCaptureError as exc:
            last_exception = exc
            logger.debug("Screenshot attempt %d failed: %s", attempt + 1, exc)
            if attempt < retries:
                continue
            # Last attempt failed
            break
        except (ADBCommandError, OSError, ValueError) as exc:
            last_exception = exc
            logger.debug("Screenshot attempt %d failed: %s", attempt + 1, exc)
            if attempt < retries:
                continue
            break

    # All attempts failed
    logger.warning("Screenshot capture failed after %d attempts", retries + 1)
    if not allow_fallback:
        if isinstance(last_exception, ScreenshotCaptureError):
            raise
        if isinstance(last_exception, ADBCommandError):
            raise ScreenshotTimeoutError(str(last_exception)) from last_exception
        raise ScreenshotCaptureError(str(last_exception)) from last_exception

    return _create_fallback_screenshot(
        device_id=device_id,
        is_sensitive=isinstance(last_exception, ScreenshotCaptureError),
        max_size=max_size,
        image_format=image_format,
        quality=quality,
        error=str(last_exception),
    )


# ============================================================================
# Internal Implementation
# ============================================================================

def _capture_screenshot_impl(
    device_id: str | None,
    timeout: int | None,
    max_size: int,
    image_format: str,
    mime_type: str,
    quality: int,
) -> Screenshot:
    """Core screenshot capture implementation."""
    result = run_adb(
        ["exec-out", "screencap", "-p"],
        device_id=device_id,
        timeout=timeout,
        check=False,
        text=False,
        retries=0,  # Retries handled at higher level
    )

    stdout = _as_bytes(result.stdout)
    stderr = _as_bytes(result.stderr)
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    # Check command execution
    if result.returncode != 0:
        stdout_text = stdout[:512].decode("utf-8", errors="replace").strip()
        diagnostic = "\n".join(part for part in (stderr_text, stdout_text) if part)
        raise ScreenshotCaptureError(
            "Android rejected screenshot capture"
            + (f": {diagnostic[:500]}" if diagnostic else "")
        )

    # Check for empty data
    if not stdout:
        raise ScreenshotCaptureError(
            "Empty screenshot data received"
            + (f": {stderr_text[:500]}" if stderr_text else "")
        )

    # Validate PNG header
    if not stdout.startswith(b"\x89PNG"):
        stdout_text = stdout[:512].decode("utf-8", errors="replace").strip()
        diagnostic = "\n".join(part for part in (stderr_text, stdout_text) if part)
        raise ScreenshotDecodeError(
            f"Unexpected screenshot stream header: {stdout[:16]!r}"
            + (f"; diagnostic: {diagnostic[:500]}" if diagnostic else "")
        )

    # Check stderr for failure markers (binary PNG may contain coincidental byte patterns)
    if any(marker in stderr_text.casefold() for marker in FAILURE_MARKERS):
        # Secure flag is a permission issue, not general failure
        if "secure flag" in stderr_text.casefold():
            raise ScreenshotPermissionError(
                f"Secure screen detected: {stderr_text[:500]}"
            )
        raise ScreenshotCaptureError(
            f"Android reported an untrustworthy screenshot: {stderr_text[:500]}"
        )

    # Decode image
    try:
        image = Image.open(BytesIO(stdout))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ScreenshotDecodeError(f"Invalid screenshot image: {exc}") from exc

    display_width, display_height = image.size
    if display_width <= 0 or display_height <= 0:
        raise ScreenshotDecodeError(
            f"Invalid screenshot dimensions: {display_width}x{display_height}"
        )

    # Process image
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


# ============================================================================
# Helper Functions
# ============================================================================

def _as_bytes(value: str | bytes | None) -> bytes:
    """Convert value to bytes safely."""
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def _normalize_image_format(image_format: str) -> str:
    """Normalize image format string to canonical form."""
    normalized = (image_format or "PNG").strip().upper()
    canonical = SUPPORTED_IMAGE_FORMATS.get(normalized)
    if canonical is None:
        logger.warning(
            "Unsupported image format '%s', falling back to PNG",
            image_format
        )
        return "PNG"
    return canonical


def _resize_image(image: Image.Image, max_size: int) -> Image.Image:
    """Resize image preserving aspect ratio if max dimension exceeds limit."""
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
    """Encode PIL Image to bytes in specified format."""
    buffered = BytesIO()
    save_kwargs: dict[str, Any] = {}

    if image_format == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        save_kwargs.update(quality=int(quality), optimize=True)
    elif image_format == "WEBP":
        save_kwargs.update(quality=int(quality), method=6)  # Slowest/best compression

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


# ============================================================================
# Resolution Handling with Caching
# ============================================================================

_resolution_cache: dict[str, tuple[int, int]] = {}

def _get_device_resolution(device_id: str | None = None) -> tuple[int, int]:
    """Get device resolution with caching."""
    cache_key = device_id or "default"

    if cache_key in _resolution_cache:
        return _resolution_cache[cache_key]

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

        # Override size takes precedence (developer options)
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
        physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        fallback_match = re.search(r"(\d+)x(\d+)", output)

        match = override_match or physical_match or fallback_match
        if match:
            width, height = int(match.group(1)), int(match.group(2))
            if width > 0 and height > 0:
                _resolution_cache[cache_key] = (width, height)
                return width, height

    except Exception as exc:
        logger.debug("Failed to query device resolution: %s", exc)

    # Default fallback
    _resolution_cache[cache_key] = DEFAULT_DEVICE_RESOLUTION
    return DEFAULT_DEVICE_RESOLUTION


def _create_fallback_screenshot(
    device_id: str | None = None,
    is_sensitive: bool = False,
    max_size: int = DEFAULT_MAX_SIZE,
    image_format: str = "PNG",
    quality: int = DEFAULT_IMAGE_QUALITY,
    error: str | None = None,
) -> Screenshot:
    """Create a placeholder black screenshot when capture fails."""
    image_format = _normalize_image_format(image_format)
    width, height = _get_device_resolution(device_id)
    display_width, display_height = width, height

    # Create black placeholder image
    image = Image.new("RGB", (width, height), color="black")
    image = _resize_image(image, max_size=max_size)
    encoded_bytes = _encode_image(image, image_format, quality)
    encoded = base64.b64encode(encoded_bytes).decode("utf-8")
    width, height = image.size

    return Screenshot(
        base64_data=encoded,
        width=width,
        height=height,
        mime_type=MIME_TYPES.get(image_format, "image/png"),
        display_width=display_width,
        display_height=display_height,
        is_sensitive=is_sensitive,
        timestamp=time.time(),
        available=False,
        error=error or "Screenshot unavailable",
        sha256=hashlib.sha256(encoded_bytes).hexdigest(),
        is_blank=True,
    )


# ============================================================================
# Utility Functions for Callers
# ============================================================================

def is_secure_screenshot_error(exc: Exception) -> bool:
    """Check if an exception indicates a secure screen (cannot capture)."""
    return isinstance(exc, ScreenshotPermissionError)


def is_transient_screenshot_error(exc: Exception) -> bool:
    """Check if an exception indicates a transient error (retryable)."""
    return isinstance(exc, ScreenshotTimeoutError) or (
        isinstance(exc, ScreenshotCaptureError)
        and "timeout" in str(exc).lower()
    )