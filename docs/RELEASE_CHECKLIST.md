# Release Checklist

Use this checklist for a tagged PhoneAgent release.

1. Confirm that `.env`, device screenshots, private trajectories, and local archives are not tracked.
2. Run `uv lock --check`, `uv run ruff check .`, `uv run pytest -q`, and `uv build`.
3. Syntax-check every `webui/static/*.js` file as an ES module, check the project-site script,
   and exercise the HTTP static routes.
4. Verify branch-aware coverage for action protocol, state, verification, recovery, and trajectory
   modules, with explicit fault cases for observation timeout, ADB disconnect, model cancellation,
   foreground mismatch, and stale Web callbacks.
5. Run `bash scripts/check_wheel.sh` after building. It installs the wheel in a clean temporary
   environment, exercises every packaged entry point, and verifies the Web Console assets.
6. Run the [dedicated-device smoke matrix](REAL_DEVICE_REGRESSION.md): launch, tap, type,
   system-panel fallback, cancellation, and one multi-step task. Record device, Android/ROM,
   model, commit, and redacted trajectories.
7. Build an externally annotated evaluation report and confirm that task correctness is not
   inferred from runtime completion.
8. Update `CHANGELOG.md`, release notes, website version text, and `CITATION.cff`.
9. Push `main`, wait for CI and Pages workflows, then create an annotated tag.
10. Push the annotated version tag. The `Release` workflow creates the GitHub Release and attaches
    the wheel, source distribution, and checksum file.

Repository: https://github.com/AuroraEchos/PhoneAgent
