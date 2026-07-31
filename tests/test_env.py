from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_env_example_uses_current_lazy_launch_configuration() -> None:
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")

    assert "PHONE_AGENT_APP_LAUNCH_TIMEOUT_SECONDS=15" in env_example
    assert "PHONE_AGENT_WEB_HOST=127.0.0.1" in env_example
    assert "PHONE_AGENT_WEB_PORT=8765" in env_example
    assert "PHONE_AGENT_APP_ALIASES_FILE" not in env_example
    assert "PHONE_AGENT_APP_CATALOG_TTL" not in env_example
    assert "PHONE_AGENT_MAX_APP_CONTEXT_CHARS" not in env_example


def test_cli_reads_lazy_launch_timeout_from_environment(monkeypatch) -> None:
    from phoneagent.cli import parse_args

    monkeypatch.setenv("PHONE_AGENT_APP_LAUNCH_TIMEOUT_SECONDS", "8.25")
    monkeypatch.setattr(sys, "argv", ["phoneagent"])

    assert parse_args().app_launch_timeout_seconds == 8.25


def test_importing_package_does_not_load_dotenv(tmp_path) -> None:
    (tmp_path / ".env").write_text("PHONE_AGENT_IMPORT_SENTINEL=loaded\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("PHONE_AGENT_IMPORT_SENTINEL", None)
    src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = str(src)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, phoneagent; "
                "assert phoneagent.__version__ == '0.1.3'; "
                "assert 'PHONE_AGENT_IMPORT_SENTINEL' not in os.environ"
            ),
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
