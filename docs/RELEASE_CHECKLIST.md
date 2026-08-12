# Release Checklist

Use this checklist for a tagged PhoneAgent release.

1. Confirm that `.env`, device screenshots, private trajectories, and local archives are not tracked.
2. Run `uv lock --check`, `uv run ruff check .`, `uv run pytest -q`, and `uv build`.
3. Syntax-check every `webui/static/*.js` file as an ES module and exercise the HTTP static routes.
4. Verify branch-aware coverage for action protocol, state, verification, recovery, and trajectory
   modules, with explicit fault cases for observation timeout, ADB disconnect, model cancellation,
   foreground mismatch, and stale Web callbacks.
5. Install the wheel in a clean environment and run `phoneagent --version`, `phoneagent --help`,
   `phoneagent-web --help`, and `phoneagent-eval --help`.
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
