"""Convenience entry point for running PhoneAgent from a source checkout."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_layout() -> None:
    src = Path(__file__).resolve().parent / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_src_layout()

from phoneagent.entrypoint import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
