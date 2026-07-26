# PhoneAgent v0.1.2

PhoneAgent `v0.1.2` is a focused runtime-consolidation release. It explicitly positions the
project as a PhoneAgent Research Runtime / Evaluation Runtime and removes duplicated or
heuristic behavior without adding horizontal capabilities.

> **Corrected release — 2026-07-26:** The original `v0.1.2` artifacts rejected valid output
> produced by the recommended `autoglm-phone` service when a single action was preceded by
> plain reasoning text. They could also reject a completed `finish(...)` call when its quoted
> message contained literal line breaks. The release was rebuilt from a corrected commit and
> the original artifacts were replaced.

## Protocol compatibility correction

- Accept one terminal `do(...)` or `finish(...)` action with optional plain reasoning text
  before it, matching the output format observed from `autoglm-phone`.
- Preserve literal CR/LF characters inside quoted action values before applying the existing
  AST and literal-only validation.
- Continue to reject JSON actions, Markdown fences, multiple actions, trailing text,
  executable expressions, malformed envelopes, unclosed strings, and incomplete calls.
- Added regression coverage derived from the failing real-device trajectory.
- Verified on a connected vivo Android device with the task `打开设置,找到无线网络界面`:
  PhoneAgent launched Settings, entered the WLAN page, parsed the multiline completion, and
  finished with `phase=completed` and zero recoveries.

## Runtime consolidation

- App aliases, launcher discovery, query resolution, and pure-launch intent handling now live
  in `phoneagent.apps.catalog` alongside the bounded catalog cache.
- `phoneagent.apps.models` and `phoneagent.apps.launcher` retain their focused responsibilities.
- Package-level imports from `phoneagent.apps` remain stable. Code importing the removed
  internal modules directly must switch to `phoneagent.apps`.
- Model prompt construction, context trimming, app-context serialization, and strict-protocol
  recovery moved from the main loop to `phoneagent.model.context`.

## Strict model action protocol

- The canonical response is `<think>...</think><answer>...</answer>`.
- One terminal `do(...)` or `finish(...)`, optionally preceded by plain reasoning text,
  remains available as a narrow compatibility path.
- JSON actions, Markdown code fences, multiple actions, extra trailing output, malformed
  envelopes, and incomplete strings are rejected rather than repaired.
- Protocol violations enter bounded strict-action recovery and are never guessed into an
  executable action.

## Minimal state and recovery model

- `AgentState.phase` is the only live phase source.
- Phase changes and execution history are stored only as trajectory events; the independent
  `TaskStateMachine` history was removed.
- Callbacks and trajectories receive the same `AgentEvent` instance, preserving timestamp,
  top-level step, message, and payload.
- Recovery is limited to replan, reobserve, retry a safe action, takeover, or abort.
- Only non-sensitive `Launch`, `Wait`, and `Home` may be retried once. Other actions are not
  automatically replayed.

## Web Console and documentation

- The Web Console now reads the app-context budget from `AppCatalogConfig`.
- Live events use `AgentEvent.step`, and event-derived model/action/verification views remain
  visible after the final `AgentState` snapshot is received.
- The English README was rewritten and the Chinese README, website, architecture document,
  configuration guidance, tests, version metadata, and release automation were aligned with
  the current runtime.

## Compatibility

- Core package imports such as `from phoneagent.apps import AppCatalog, AppResolver` remain
  supported.
- Direct imports from removed internal app modules and `TaskStateMachine` are intentionally no
  longer supported.
- The CLI and `phoneagent-web` entry points remain available.
- Trajectory schema version remains `1.0`.

## Upgrade

```bash
git pull
uv sync --extra dev
uv run phoneagent --version
uv run phoneagent-web --open-browser
```

Evaluation-suite integration is intentionally deferred; downstream evaluation code should
adapt to this runtime contract rather than adding compatibility layers back into PhoneAgent.
