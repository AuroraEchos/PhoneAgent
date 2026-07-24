# PhoneAgent Architecture

This document describes PhoneAgent `v0.1.2` as implemented in the repository. PhoneAgent is
deliberately scoped as a Research Runtime / Evaluation Runtime for real Android devices.

## Runtime overview

```text
CLI / Web Console
  -> environment, device and model preflight
  -> PhoneAgent.run(task)
  -> app catalog and task initialization
  -> Observe
  -> Build bounded model context
  -> Plan one strict action
  -> Parse and validate
  -> Execute through ADB
  -> Verify evidence
  -> Continue, recover, request takeover, or terminate
  -> atomically persist the trajectory
```

The runtime does not attempt to be a general workflow framework. Its contract is a bounded,
inspectable Android execution loop with explicit trust boundaries.

## State and events

`AgentState.phase` is the only live phase source. `AgentState` stores the current working
state needed by the loop: goal, phase, step, current and target apps, latest observation,
latest execution result, failure counters, final status, and timestamps.

`AgentState.transition(...)` validates legal phase changes and returns an event payload. It
does not keep a second transition-history object. Historical phase changes, model output,
actions, verification, and recovery decisions exist only in the trajectory event stream.

Every runtime event is created once as an `AgentEvent`. The same event instance is sent to
the callback and serialized by `TrajectoryRecorder`, preventing timestamp, step, message, or
payload drift between live integrations and saved trajectories.

## Main components

### Entry points and configuration

- `phoneagent.entrypoint` explicitly loads `.env` before entering the CLI.
- `phoneagent.cli` performs preflight checks, validates arguments, and builds runtime
  configuration.
- `phoneagent-web` provides a localhost debugging console that consumes `AgentEvent` updates.
- Importing `phoneagent` as a library does not load `.env`, connect to a device, or create a
  model client.
- Common research parameters appear in default `--help`; advanced bounds remain available as
  CLI flags or environment variables.

App-context character limits belong to `AppCatalogConfig.prompt_char_budget`. There is no
second Agent-level app-context budget or duplicate context-injection switch.

### Android device layer

- `phoneagent.adb` contains parameterized ADB command, connection, screenshot, and input
  primitives.
- `phoneagent.devices.android.AndroidDevice` exposes the device interface used by the runtime.
- Model coordinates use the normalized `[0, 999]` space and are converted to the active device
  resolution before execution.

### App catalog and deterministic routing

The application domain has three implementation files:

- `phoneagent.apps.catalog` contains alias handling, discovery, resolution, task-intent
  extraction, and the bounded catalog cache.
- `phoneagent.apps.models` contains app-domain value objects.
- `phoneagent.apps.launcher` contains deterministic launch behavior.

The supported public imports remain available from `phoneagent.apps`. Direct imports from
the former internal `aliases`, `discovery`, `intents`, or `resolver` modules are not supported.

Only a high-confidence pure open-app goal may take the deterministic launch shortcut. Other
tasks receive compact, task-relevant app context and continue through the visual loop.

### Model context and strict action protocol

`phoneagent.model.context` owns screenshot-backed prompt construction, prior-execution
summaries, app-context serialization, context trimming, and compact strict-protocol recovery.
`phoneagent.agent` remains responsible for orchestration rather than prompt-history mechanics.

The canonical response is:

```xml
<think>brief reasoning</think>
<answer>do(action="Tap", element=[500, 300])</answer>
```

A single plain `do(...)` or `finish(...)` is accepted as a narrow compatibility path. JSON,
Markdown fenced code, multiple calls, extra trailing text, malformed envelopes, and incomplete
strings are rejected. The runtime does not guess or repair an executable action.

Accepted action text is parsed with Python AST/literal handling and validated against the
action allow-list and parameter constraints. Model output is never evaluated or executed as
Python code. A protocol failure enters the existing bounded strict-action recovery path.

### Execution and confirmation

`ActionHandler` maps one validated action to Android operations. Supported operations include
launch, tap, type, swipe, back, home, double tap, long press, wait, note, API callback, user
interaction/takeover, and finish.

Actions marked sensitive, requiring confirmation, or detected as high-risk are paused at the
configured confirmation callback. Rejection is terminal for that action and is never
overridden by recovery.

### Verification semantics

Verification keeps three claims separate:

```text
command_success
observable_effect_verified
semantic_effect_verified
```

- Command success means the Android/ADB operation completed.
- Observable effect means a foreground-app or sufficient visual change was measured.
- Semantic effect requires deterministic evidence that the requested effect occurred.

For coordinate actions, visual change is not independent semantic proof. Status and navigation
bar regions are excluded from image comparison to reduce false positives.

### Minimal recovery policy

Recovery has only five strategies:

```text
REPLAN · REOBSERVE · RETRY_ACTION · TAKEOVER · ABORT
```

Recovery is bounded per failure episode and per task. `Launch`, `Wait`, and `Home` may receive
one retry when they are not marked sensitive. `Tap`, `Type`, `Swipe`, `Back`, `Double Tap`, and
`Long Press` are never blindly replayed. Relaunch, backtrack, and home-reset are not separate
recovery branches; the model can select explicit navigation actions after a fresh observation.

### Trajectory

`TrajectoryRecorder` writes a temporary JSON file and atomically replaces the final path.
Trajectory schema version remains `1.0` in PhoneAgent `v0.1.2`.

Each event contains its type, timestamp, message, payload, and optional top-level step. The
final state snapshot is included for convenience, but the event stream is authoritative for
execution history.

Trajectories may contain task text, model content, packages, timestamps, action parameters,
and evidence. They must be reviewed and redacted before publication.

## Trust boundaries

PhoneAgent `v0.1.2` does not claim independent task-level correctness:

- screen change does not prove that a coordinate target was semantically correct;
- secure or protected surfaces may be unobservable;
- the planning model currently reports full task completion through `finish(...)`;
- deterministic verification is only possible when Android state exposes sufficient evidence;
- real-device behavior varies by Android version, vendor ROM, launcher, permissions, and model
  provider.
