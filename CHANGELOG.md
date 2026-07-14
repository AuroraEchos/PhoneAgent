# Changelog

All notable changes to PhoneAgent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public releases.

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
