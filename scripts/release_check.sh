#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "[1/9] Checking forbidden tracked files"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  forbidden="$(git ls-files .env .venv runs build dist '*.egg-info' || true)"
  if [[ -n "$forbidden" ]]; then
    echo "Forbidden files are tracked:" >&2
    echo "$forbidden" >&2
    exit 1
  fi
fi

echo "[2/9] Checking placeholders and likely credentials"
if grep -RInE \
  'your-username|your-repository|your-github-name|<repository-url>|<your-repository-url>|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----' \
  README.md README_EN.md CONTRIBUTING.md docs src .github 2>/dev/null; then
  echo "Release-blocking placeholder or credential-like text found." >&2
  exit 1
fi

echo "[3/9] Compiling Python sources"
uv run python -m compileall -q src tests webui

echo "[4/9] Running Ruff"
uv run ruff check .

echo "[5/9] Checking Web Console modules"
for file in webui/static/*.js; do
  node --input-type=module --check < "$file"
done
node --check docs/script.js

echo "[6/9] Running tests"
uv run pytest -q

echo "[7/9] Building distributions"
rm -rf build dist phoneagent.egg-info src/phoneagent.egg-info
uv build

echo "[8/9] Verifying artifacts"
uv run python - <<'PY'
from pathlib import Path
import hashlib

import phoneagent

root = Path("dist")
version = phoneagent.__version__
metadata_checks = {
    "CITATION.cff": f'version: "{version}"',
    "CHANGELOG.md": f"## [{version}]",
    "docs/index.html": f">v{version}<",
    "docs/script.js": f"/releases/tag/v{version}",
}
for filename, marker in metadata_checks.items():
    text = Path(filename).read_text(encoding="utf-8")
    if marker not in text:
        raise SystemExit(f"{filename} does not contain release marker {marker!r}")
if not Path(f"RELEASE_NOTES_v{version}.md").is_file():
    raise SystemExit(f"Missing RELEASE_NOTES_v{version}.md")
artifacts = sorted(root.glob(f"phoneagent-{version}*"))
if not artifacts:
    raise SystemExit(f"No v{version} distribution artifacts were built")

lines = []
for path in artifacts:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.name}")
Path("dist/SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
PY

echo "[9/9] Installing and exercising the wheel"
bash scripts/check_wheel.sh

echo "Release checks passed."
