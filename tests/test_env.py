from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

from phoneagent import cli


def test_env_example_uses_current_lazy_launch_configuration() -> None:
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")

    assert "APP_LAUNCH_TIMEOUT_SECONDS=15" in env_example
    assert "WEB_HOST=127.0.0.1" in env_example
    assert "WEB_PORT=8765" in env_example
    assert "APP_ALIASES_FILE" not in env_example
    assert "APP_CATALOG_TTL" not in env_example
    assert "MAX_APP_CONTEXT_CHARS" not in env_example


def test_cli_reads_lazy_launch_timeout_from_environment(monkeypatch) -> None:
    from phoneagent.cli import parse_args

    monkeypatch.setenv("APP_LAUNCH_TIMEOUT_SECONDS", "8.25")
    monkeypatch.setattr(sys, "argv", ["phoneagent"])

    assert parse_args().app_launch_timeout_seconds == 8.25


def test_importing_package_does_not_load_dotenv(tmp_path) -> None:
    (tmp_path / ".env").write_text("IMPORT_SENTINEL=loaded\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("IMPORT_SENTINEL", None)
    src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = str(src)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, phoneagent; "
                "assert phoneagent.__version__ == '0.1.4'; "
                "assert 'IMPORT_SENTINEL' not in os.environ"
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_successful_device_command_stops_cli_dispatch(monkeypatch) -> None:
    args = Namespace(
        list_configured_apps=False,
        list_apps=False,
        device_id=None,
    )
    monkeypatch.setattr(cli, "_parse_arguments", lambda: args)
    monkeypatch.setattr(cli, "_handle_device_commands", lambda _args: 0)

    def unexpected_config_build(_args):
        raise AssertionError("device commands must not continue into agent configuration")

    monkeypatch.setattr(cli, "_build_cli_config", unexpected_config_build)

    assert cli.main() == 0
