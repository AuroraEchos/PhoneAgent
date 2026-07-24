# PhoneAgent v0.1.2

PhoneAgent `v0.1.2` is a focused runtime-consolidation release. It explicitly positions the
project as a PhoneAgent Research Runtime / Evaluation Runtime and removes duplicated or
heuristic behavior without adding horizontal capabilities.

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
- One plain `do(...)` or `finish(...)` remains available as a narrow compatibility path.
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
