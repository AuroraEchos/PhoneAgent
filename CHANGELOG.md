# Changelog

All notable changes to PhoneAgent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public releases.

## [0.1.1] - 2026-07-24

### Added

- Local Web Console for submitting tasks, following live execution events, responding to sensitive-operation and takeover prompts, and browsing saved trajectories.
- One-time device and model preflight checks that are reused for the lifetime of a Web Console server session.
- Installable `phoneagent-web` command with packaged frontend assets.
- Tag-triggered GitHub Release automation with version validation, tests, distributions, and SHA-256 checksums.

### Changed

- Refined the project website layout, visual presentation, examples, and architecture diagram.
- Aligned website descriptions with the implemented runtime behavior and current project boundaries.
- Made release artifact validation derive its target version from the package.

### Safety and reliability

- Model API checks and runtime requests no longer inherit ambient HTTP proxy settings.
- The Web Console listens on localhost by default, rejects cross-origin control requests, and applies restrictive browser security headers.
- Trajectory access is limited to validated files inside the configured trajectory directory.
- Core PhoneAgent command-line and Python APIs remain compatible with `v0.1.0`; trajectory schema version remains `1.0`.

## [0.1.0] - 2026-07-14

### Added

- Android screenshot-driven observe-plan-execute loop.
- OpenAI-compatible vision-language model client with streaming support.
- Safe AST/JSON action parser and argument validation.
- ADB-backed action executor and ADB Keyboard text input.
- Dynamic discovery and confidence-aware resolution of launchable applications.
- Deterministic package/activity launch for high-confidence pure launch tasks.
- Explicit task-level state machine.
- Structured post-action verification with command, observable-effect, and semantic-effect fields.
- Bounded recovery, manual takeover, and atomic trajectory recording.
- Unit and integration-style tests that do not require a connected device.
- GitHub Actions checks for Python 3.12.

### Safety and reliability

- Launcher search fallback now fails when no foreground or visual change is observed.
- `Back` is excluded from automatic action replay.
- Per-failure recovery attempts reset after a successful accepted step.
- Importing the package no longer loads `.env` or performs runtime initialization.
- The package uses the standard `src/phoneagent/` layout.
