"""Environment file loading utilities."""

from __future__ import annotations

import os
from pathlib import Path


def load_env(env_path: str | os.PathLike[str] | None = None, *, override: bool = False) -> bool:
    """Load configuration from a ``.env`` file if one exists.

    Real environment variables win by default.  This keeps shell-provided
    secrets and CI configuration authoritative while still making local
    development convenient.
    """
    path = Path(env_path) if env_path is not None else _find_project_env()
    if path is None or not path.exists():
        return False

    try:
        from dotenv import load_dotenv
    except ImportError:
        return _load_simple_env(path, override=override)

    return bool(load_dotenv(path, override=override))


def _find_project_env() -> Path | None:
    try:
        current = Path.cwd().resolve()
    except OSError:
        # A process can outlive a deleted working directory (for example in
        # temporary test environments). Fall back to the user home safely.
        current = Path.home().resolve()
    candidates = [current, *current.parents]

    # In a source checkout, locate the repository root by marker rather than
    # relying on a fixed package depth. Installed wheels may not have one.
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            if parent not in candidates:
                candidates.append(parent)
            break

    for directory in candidates:
        path = directory / ".env"
        if path.exists():
            return path
    return None


def _load_simple_env(path: Path, *, override: bool) -> bool:
    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _clean_value(value.strip())
        if not key or (key in os.environ and not override):
            continue
        os.environ[key] = value
        loaded = True
    return loaded


def _clean_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

