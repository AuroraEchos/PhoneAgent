#!/usr/bin/env python3
"""Generate the deterministic PhoneAgent social-preview image."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "og-image.png"
WIDTH = 1200
HEIGHT = 630


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)
        color = tuple(round(start + (end - start) * ratio) for start, end in zip(top, bottom))
        for x in range(WIDTH):
            pixels[x, y] = color
    return image


def _glow(
    image: Image.Image,
    box: tuple[int, int, int, int],
    color: tuple[int, int, int, int],
    blur: int,
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color)
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def _draw_logo(image: Image.Image, origin: tuple[int, int], size: int) -> None:
    x, y = origin
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (x, y, x + size, y + size),
        radius=round(size * 0.31),
        fill=(186, 101, 75, 255),
    )
    phone = (
        x + round(size * 0.27),
        y + round(size * 0.16),
        x + round(size * 0.73),
        y + round(size * 0.84),
    )
    draw.rounded_rectangle(phone, radius=round(size * 0.13), outline=(255, 255, 255), width=5)
    draw.line(
        (
            x + round(size * 0.36),
            y + round(size * 0.32),
            x + round(size * 0.64),
            y + round(size * 0.32),
        ),
        fill=(255, 255, 255),
        width=4,
    )
    draw.ellipse(
        (
            x + round(size * 0.47),
            y + round(size * 0.72),
            x + round(size * 0.53),
            y + round(size * 0.78),
        ),
        fill=(255, 255, 255),
    )
    draw.arc(
        (
            x + round(size * 0.66),
            y + round(size * 0.42),
            x + round(size * 0.94),
            y + round(size * 0.70),
        ),
        start=270,
        end=360,
        fill=(211, 230, 222),
        width=4,
    )
    image.alpha_composite(layer)


def main() -> None:
    image = _vertical_gradient((8, 11, 18), (13, 17, 27)).convert("RGBA")
    _glow(image, (700, -250, 1330, 380), (139, 124, 255, 70), 110)
    _glow(image, (-280, 310, 390, 900), (51, 130, 210, 50), 125)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (56, 52, WIDTH - 56, HEIGHT - 52),
        radius=34,
        fill=(17, 22, 35, 226),
        outline=(255, 255, 255, 28),
        width=2,
    )

    _draw_logo(image, (104, 96), 92)
    draw.text((220, 105), "PhoneAgent", font=_font(52, bold=True), fill=(247, 249, 253))
    draw.text(
        (222, 163),
        "RESEARCH & EVALUATION RUNTIME",
        font=_font(18, bold=True),
        fill=(169, 159, 255),
    )

    draw.text(
        (104, 248),
        "Vision-Driven Android\nAgent Runtime",
        font=_font(58, bold=True),
        fill=(245, 247, 251),
        spacing=4,
    )
    draw.text(
        (107, 399),
        "Structured actions · verified effects · auditable trajectories",
        font=_font(22),
        fill=(174, 183, 202),
    )

    stages = ("OBSERVE", "PLAN", "EXECUTE", "VERIFY", "RECOVER")
    stage_x = 104
    for index, stage in enumerate(stages):
        width = 97 if stage != "EXECUTE" else 108
        draw.rounded_rectangle(
            (stage_x, 475, stage_x + width, 518),
            radius=21,
            fill=(25, 31, 48, 255),
            outline=(139, 124, 255, 95),
            width=1,
        )
        draw.text(
            (stage_x + width / 2, 496),
            stage,
            font=_font(13, bold=True),
            fill=(218, 222, 234),
            anchor="mm",
        )
        stage_x += width + 13
        if index < len(stages) - 1:
            draw.line((stage_x - 9, 496, stage_x - 4, 496), fill=(77, 216, 230), width=2)

    panel = (796, 120, 1085, 510)
    draw.rounded_rectangle(panel, radius=30, fill=(10, 14, 24, 245), outline=(255, 255, 255, 30), width=2)
    draw.rounded_rectangle((824, 146, 1057, 195), radius=14, fill=(24, 30, 46, 255))
    draw.ellipse((846, 164, 860, 178), fill=(95, 221, 157))
    draw.text((875, 159), "Runtime active", font=_font(18, bold=True), fill=(235, 239, 248))

    cards = (
        ("01", "Observe", "Screenshot captured", (77, 216, 230)),
        ("02", "Plan", "One strict action", (139, 124, 255)),
        ("03", "Execute", "ADB command bounded", (92, 156, 255)),
        ("04", "Verify", "Evidence recorded", (95, 221, 157)),
    )
    card_y = 218
    for number, title, detail, accent in cards:
        draw.rounded_rectangle(
            (824, card_y, 1057, card_y + 58),
            radius=14,
            fill=(20, 25, 40, 255),
            outline=(*accent, 75),
            width=1,
        )
        draw.text((842, card_y + 17), number, font=_font(14, bold=True), fill=accent)
        draw.text((881, card_y + 10), title, font=_font(17, bold=True), fill=(241, 244, 250))
        draw.text((881, card_y + 32), detail, font=_font(12), fill=(133, 144, 166))
        card_y += 68

    image.convert("RGB").save(OUTPUT, format="PNG", optimize=True)
    print(f"Generated {OUTPUT} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
