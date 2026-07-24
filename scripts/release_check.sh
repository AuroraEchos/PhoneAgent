#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "[1/7] Checking forbidden tracked files"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  forbidden="$(git ls-files .env .venv runs build dist '*.egg-info' || true)"
  if [[ -n "$forbidden" ]]; then
    echo "Forbidden files are tracked:" >&2
    echo "$forbidden" >&2
    exit 1
  fi
fi

echo "[2/7] Checking placeholders and likely credentials"
if grep -RInE \
  'your-username|your-repository|your-github-name|<repository-url>|<your-repository-url>|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----' \
  README.md README_EN.md CONTRIBUTING.md docs src examples .github 2>/dev/null; then
  echo "Release-blocking placeholder or credential-like text found." >&2
  exit 1
fi

echo "[3/7] Compiling Python sources"
uv run python -m compileall -q src tests main.py

echo "[4/7] Running Ruff"
uv run ruff check .

echo "[5/7] Running tests"
uv run pytest -q

echo "[6/7] Building distributions"
rm -rf build dist src/phoneagent.egg-info
uv build

echo "[7/7] Verifying artifacts"
uv run python - <<'PY'
from pathlib import Path
import hashlib

import phoneagent

root = Path("dist")
version = phoneagent.__version__
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

echo "Release checks passed."
