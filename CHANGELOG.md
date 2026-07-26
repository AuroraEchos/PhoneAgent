# Changelog

All notable changes to PhoneAgent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public releases.

## [0.1.2] - 2026-07-25; corrected 2026-07-26

### Fixed in corrected release

- Fixed a strict-protocol regression that rejected the recommended `autoglm-phone` response
  format when plain reasoning text preceded one terminal `do(...)` or `finish(...)` call.
- Accepted literal line breaks inside closed, quoted action values while retaining AST-based,
  literal-only argument validation.
- Added regression tests for the real-device failure and republished the `v0.1.2` artifacts
  from the corrected commit.
- Added a narrow, provider-neutral coordinate syntax adapter for explicit `<point>`,
  `<point_2d>`, special point-token, and exact `{x, y}` action coordinates.
- Kept bounding boxes, unknown tags, multiple points, non-numeric or executable values, extra
  coordinate keys, and out-of-range coordinates behind the strict rejection boundary.
- Added model-facing coordinate-format guidance and marker-aware recovery feedback, verified
  by trajectory replay and a zero-recovery real-device run against another multimodal provider.

### Changed

- Reframed PhoneAgent as a focused Research Runtime / Evaluation Runtime without adding horizontal capabilities.
- Consolidated app aliases, discovery, resolution, and pure-launch intent handling into `phoneagent.apps.catalog`; package-level imports from `phoneagent.apps` remain stable.
- Restricted model output to the canonical `<think>/<answer>` envelope or one terminal `do(...)` / `finish(...)` compatibility call with optional preceding reasoning text.
- Removed JSON, fenced-code, multi-action, trailing-text, and incomplete-string action repair.
- Reduced recovery to `REPLAN`, `REOBSERVE`, `RETRY_ACTION`, `TAKEOVER`, and `ABORT`.
- Made `AgentState.phase` the single live phase source and the trajectory event stream the only phase and execution history.
- Moved model-context construction, trimming, app-context serialization, and protocol recovery into `phoneagent.model.context`.
- Moved the app-context character budget to `AppCatalogConfig.prompt_char_budget` and reduced the default CLI help surface.
- Updated the Web Console to consume top-level `AgentEvent.step` and preserve event-derived thinking, action, verification, and recovery views after task completion.
- Rewrote the English README and aligned the website and architecture documentation with the implemented runtime.

### Removed

- Internal app modules `aliases`, `discovery`, `intents`, and `resolver`.
- The independent `TaskStateMachine` transition history.
- Separate relaunch, backtrack, and home-reset recovery branches.
- Duplicate Agent-level app-context and strict-recovery configuration switches.

### Safety and reliability

- Protocol violations enter bounded strict-action recovery instead of guessed execution.
- Only non-sensitive `Launch`, `Wait`, and `Home` actions may receive one automatic retry.
- Callback consumers and trajectories receive the same `AgentEvent` timestamp, step, message, and payload.
- Trajectory schema version remains `1.0`.

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
