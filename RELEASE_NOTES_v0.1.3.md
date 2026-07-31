# PhoneAgent v0.1.3

PhoneAgent `v0.1.3` simplifies application launching, substantially refreshes the local Web
Console, and aligns runtime configuration and documentation with the new execution model.

## Unified task execution

- Every task now follows the same screenshot-backed observe, plan, execute, verify, and recover
  loop, including tasks whose first step is opening an application.
- Removed startup-time application discovery, catalog caching, fuzzy resolution, prompt app
  context, pure-launch shortcuts, and Launcher-search fallback.
- A model-issued `Launch` resolves only when it is executed, using either a built-in static alias
  or an explicit Android package name.
- The Android device layer checks installation through PackageManager, starts the package through
  ADB under a bounded timeout, and returns a compact structured result for verification.
- Foreground-package evidence remains the deterministic semantic check for successful launches.

## Application compatibility registry

- Moved the supported human-readable application names to the static
  `phoneagent.config.apps.APP_PACKAGES` compatibility registry.
- Expanded the registry for common social, finance, shopping, travel, media, productivity,
  education, AI, system, and international applications.
- `phoneagent --list-configured-apps` lists built-in aliases without querying a device.
- `phoneagent --list-apps` reports only configured packages installed on the selected device;
  it is intentionally not a complete dynamic catalog.
- Unknown human-readable names return `app_not_found`, while configured but absent packages
  return `app_not_installed`. Exact installed package names remain accepted.

## Web Console redesign

- Replaced the card-oriented dashboard with a conversation-style workspace inspired by modern
  AI chat interfaces.
- Added a collapsible task-history sidebar, responsive mobile drawer, bottom task composer,
  continuous execution timeline, live waiting animation, and saved-trajectory detail view.
- Added a dedicated startup preflight gate. The main workspace remains blurred and unavailable
  until the device and model checks pass, then opens automatically.
- Removed the old startup-check card from the main workspace and consolidated the ready state,
  selected device, and model identity in the lower-right runtime footer.
- Preserved one checked PhoneAgent instance per Web server session so subsequent tasks avoid
  repeating startup checks.

## Configuration and documentation

- Added shared `PHONE_AGENT_APP_LAUNCH_TIMEOUT_SECONDS` handling to both CLI and Web Console
  runtime construction.
- Removed obsolete catalog TTL, app prompt candidate, app-context budget, and custom alias-file
  settings from `.env.example`.
- Added Web Console host and port examples to `.env.example`.
- Updated the Chinese and English READMEs, Web Console guide, architecture document, changelog,
  release guide, and bilingual project website for the current runtime.
- Removed obsolete application-alias and trajectory examples that documented retired interfaces.

## Compatibility

- The `phoneagent.apps` package and its catalog, resolver, intent, launcher, and app-domain model
  imports have been removed. Use `phoneagent.config.apps` for the compatibility registry and
  `phoneagent.devices` for launch result types.
- The `phoneagent` and `phoneagent-web` command-line entry points remain available.
- The strict terminal `<answer>...</answer>` action protocol introduced in the corrected
  `v0.1.2` release is unchanged.
- Trajectory schema version remains `1.0`.

## Validation

- Ruff lint and formatting checks pass.
- Python source compilation and JavaScript syntax checks pass.
- The complete suite passes with 61 tests and 17 subtests.
- Lockfile, CLI help, Web Console help, and distribution build checks pass.

## Upgrade

```bash
git pull
uv sync --extra dev
uv run phoneagent --version
uv run phoneagent-web --open-browser
```

Users importing the removed `phoneagent.apps` APIs must migrate before upgrading. Users of the
CLI, Web Console, strict model action protocol, and trajectory schema can upgrade directly.
