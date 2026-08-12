#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

mapfile -t wheels < <(find dist -maxdepth 1 -type f -name '*.whl' -print | sort)
if [[ "${#wheels[@]}" -ne 1 ]]; then
  echo "Expected exactly one wheel in dist, found ${#wheels[@]}." >&2
  exit 1
fi

wheel_check_dir="$(mktemp -d "${TMPDIR:-/tmp}/phoneagent-wheel-check.XXXXXX")"
trap 'rm -rf -- "$wheel_check_dir"' EXIT

uv venv "$wheel_check_dir/.venv"
uv pip install --python "$wheel_check_dir/.venv/bin/python" "${wheels[0]}"

(
  cd "$wheel_check_dir"
  .venv/bin/phoneagent --version
  .venv/bin/phoneagent --help >/dev/null
  .venv/bin/phoneagent-web --help >/dev/null
  .venv/bin/phoneagent-eval --help >/dev/null
  .venv/bin/python - <<'PY'
from importlib.metadata import version
from importlib.resources import files

import phoneagent

if phoneagent.__version__ != version("phoneagent"):
    raise SystemExit("Installed package metadata and runtime version disagree")

required_assets = ("api.js", "app.js", "index.html", "state.js", "timeline.js", "usage.js")
missing = [name for name in required_assets if not (files("webui") / "static" / name).is_file()]
if missing:
    raise SystemExit(f"Wheel is missing Web Console assets: {', '.join(missing)}")
PY
)

echo "Clean-wheel checks passed."
