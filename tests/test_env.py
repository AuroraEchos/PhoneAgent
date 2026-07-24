from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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
                "assert phoneagent.__version__ == '0.1.1'; "
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
