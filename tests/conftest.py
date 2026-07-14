from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from phoneagent.adb.screenshot import Screenshot
from phoneagent.devices import ScreenObservation


def make_screenshot(
    value: int,
    *,
    width: int = 64,
    height: int = 64,
    available: bool = True,
) -> Screenshot:
    image = Image.new("RGB", (width, height), (value, value, value))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return Screenshot(
        base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"),
        width=width,
        height=height,
        display_width=width,
        display_height=height,
        available=available,
        is_blank=False,
    )


def make_observation(
    value: int,
    *,
    app: str = "System Home",
    package: str | None = None,
) -> ScreenObservation:
    return ScreenObservation(
        screenshot=make_screenshot(value),
        current_app=app,
        current_package=package,
    )
