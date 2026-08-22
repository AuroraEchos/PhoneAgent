#!/usr/bin/env python3
"""Validate dependency-free documentation-site assets."""

from __future__ import annotations

import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OG_IMAGE = DOCS / "assets" / "og-image.png"
EXPECTED_OG_SIZE = (1200, 630)
EXPECTED_OG_URL = "https://auroraechos.github.io/PhoneAgent/assets/og-image.png"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SystemExit(f"{path.relative_to(ROOT)} is not a valid PNG")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    required = (
        DOCS / "index.html",
        DOCS / "guide.html",
        DOCS / "script.js",
        DOCS / "guide.js",
        DOCS / "assets" / "logo.svg",
        DOCS / "assets" / "favicon.svg",
        OG_IMAGE,
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing documentation-site assets: " + ", ".join(missing))

    size = _png_size(OG_IMAGE)
    if size != EXPECTED_OG_SIZE:
        raise SystemExit(
            f"docs/assets/og-image.png must be {EXPECTED_OG_SIZE[0]}x{EXPECTED_OG_SIZE[1]}, "
            f"got {size[0]}x{size[1]}"
        )

    for filename in ("index.html", "guide.html"):
        text = (DOCS / filename).read_text(encoding="utf-8")
        if f'property="og:image" content="{EXPECTED_OG_URL}"' not in text:
            raise SystemExit(f"docs/{filename} does not reference the social-preview image")
        if f'name="twitter:image" content="{EXPECTED_OG_URL}"' not in text:
            raise SystemExit(f"docs/{filename} does not expose the Twitter preview image")

    guide_script = (DOCS / "guide.js").read_text(encoding="utf-8")
    guide_files = sorted(set(re.findall(r'file:\s*"([A-Za-z0-9_-]+\.md)"', guide_script)))
    if not guide_files:
        raise SystemExit("docs/guide.js does not declare any subsystem documents")
    missing_guides = [name for name in guide_files if not (DOCS / "subsystems" / name).is_file()]
    if missing_guides:
        raise SystemExit("Missing subsystem guides: " + ", ".join(missing_guides))

    print(
        f"Static site checks passed: {len(guide_files)} guide documents, "
        f"OG image {size[0]}x{size[1]}."
    )


if __name__ == "__main__":
    main()
