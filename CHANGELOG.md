# Changelog

All notable changes to PhoneAgent will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses semantic versioning for public releases.

## [0.1.3] - 2026-07-31

### Added

- A conversation-style Web Console with a collapsible task-history sidebar, bottom composer,
  continuous execution timeline, responsive navigation, and saved-trajectory detail view.
- A dedicated startup preflight gate that keeps the console blurred and unavailable until the
  device and model checks pass.
- Built-in static compatibility aliases for common Android applications and explicit CLI
  commands for listing configured aliases or their installed intersection.
- Shared `PHONE_AGENT_APP_LAUNCH_TIMEOUT_SECONDS`, Web Console host/port examples, and regression
  coverage for the current environment contract.

### Changed

- Every task now enters the same observe, plan, execute, verify, and recover loop; application
  launch no longer uses a pure-launch shortcut or startup-time application context.
- A model-issued `Launch` is resolved lazily through a static alias or explicit package, checked
  with PackageManager, started through ADB, and verified against the foreground package.
- Simplified the agent orchestration, model context, action handling, verification, recovery,
  runtime events, and Android device boundaries around the new launch contract.
- Refined the Web Console identity footer, vertically centered composer, live waiting state,
  sidebar behavior, and scrollbar presentation.
- Synchronized `.env.example`, CLI/Web runtime configuration, READMEs, architecture documentation,
  release guidance, and the bilingual project website with the implemented runtime.

### Removed

- The `phoneagent.apps` catalog, discovery, fuzzy resolver, intent, launcher, and app-domain model
  package.
- Startup application enumeration, catalog caching, prompt application injection, Launcher-search
  fallback, custom alias files, and their obsolete environment settings.
- Obsolete application-alias and trajectory example files that described the retired interfaces.

### Safety and reliability

- Unknown aliases and absent packages now return compact structured failures instead of entering
  heuristic launcher search.
- The Web Console continues to reuse one checked runtime per server session and exposes control
  only after preflight succeeds.
- Trajectory schema version remains `1.0`; the synchronized suite passes 61 tests and 17 subtests.

## [0.1.2] - 2026-07-25; corrected 2026-07-27

### Fixed in corrected release

- Replaced the dual `<think>/<answer>` model envelope and temporary unwrapped-action
  compatibility path with one terminal `<answer>...</answer>` executable boundary.
- Treat all text before the answer block as inert reasoning, require exactly one complete answer
  block, and reject unwrapped actions or any output after `</answer>`.
- Serialize assistant history with the answer block alone so subsequent turns do not imitate the
  removed thinking-tag format.
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
- Replayed the malformed-envelope failure and completed a real-device WLAN navigation task with
  `glm-4.6v-flash`: all four responses used answer-only output, with no model-protocol errors.

### Changed

- Reframed PhoneAgent as a focused Research Runtime / Evaluation Runtime without adding horizontal capabilities.
- Consolidated app aliases, discovery, resolution, and pure-launch intent handling into `phoneagent.apps.catalog`; package-level imports from `phoneagent.apps` remain stable.
- Restricted executable model output to one terminal `<answer>...</answer>` block; any preceding
  text is non-executable reasoning.
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
