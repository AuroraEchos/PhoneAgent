"""Console entry point that loads local environment configuration explicitly."""

from __future__ import annotations


def main() -> int:
    from phoneagent.config.env import load_env

    load_env()

    from phoneagent.cli import main as cli_main

    return cli_main()
