"""Console entry point that loads local environment configuration explicitly."""

from __future__ import annotations


def main() -> int:
    from phoneagent.config.env import load_env

    load_env()

    # Import after loading .env so dataclass defaults and timing configuration
    # observe the intended process environment.
    from phoneagent.cli import main as cli_main

    return cli_main()
