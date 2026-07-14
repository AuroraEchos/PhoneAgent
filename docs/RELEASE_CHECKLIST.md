# Release Checklist

Use this checklist for a tagged PhoneAgent release.

1. Confirm that `.env`, device screenshots, private trajectories, and local archives are not tracked.
2. Run `uv lock --check`, `uv run ruff check .`, `uv run pytest -q`, and `uv build`.
3. Install the wheel in a clean environment and run `phoneagent --version` and `phoneagent --help`.
4. Update `CHANGELOG.md`, release notes, website version text, and `CITATION.cff`.
5. Push `main`, wait for CI and Pages workflows, then create an annotated tag.
6. Create the GitHub Release and attach the wheel, source distribution, and checksum file.

Repository: https://github.com/AuroraEchos/PhoneAgent
