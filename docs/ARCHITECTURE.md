# PhoneAgent Architecture

This document describes PhoneAgent `v0.1.3` as implemented in the repository. PhoneAgent is
deliberately scoped as a Research Runtime / Evaluation Runtime for real Android devices.

## Runtime overview

```text
CLI / Web Console
  -> environment, device and model preflight
  -> PhoneAgent.run(task)
  -> lightweight task and state initialization
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

Application launching has one advanced bound, `app_launch_timeout_seconds`, exposed through
`PHONE_AGENT_APP_LAUNCH_TIMEOUT_SECONDS`. There is no application-catalog TTL, discovery pass,
prompt candidate limit, or app-context injection switch.

### Android device layer

- `phoneagent.adb` contains parameterized ADB command, connection, screenshot, and input
  primitives.
- `phoneagent.devices.android.AndroidDevice` exposes the device interface used by the runtime.
- Model coordinates use the normalized `[0, 999]` space and are converted to the active device
  resolution before execution.

### Lazy deterministic app launch

PhoneAgent does not enumerate applications when a task starts and does not bypass the planner
for pure open-app goals. Every task enters the same observation and one-action model loop.

When the model emits `do(action="Launch", app=...)`:

1. `phoneagent.config.apps` resolves a built-in human-readable alias or accepts an explicit
   Android package name.
2. `AndroidDevice.launch_app_resolved(...)` uses `pm path` to check that the package is installed.
3. The ADB device layer sends a launcher intent through `monkey` under a bounded timeout.
4. Post-action verification compares the observed foreground package with the expected package.

Unknown aliases return `app_not_found`; configured but absent packages return
`app_not_installed`. Both are structured execution failures. `--list-apps` reports only the
intersection between configured packages and packages installed on the selected device; it is
not a complete dynamic application catalog.

### Model context and strict action protocol

`phoneagent.model.context` owns screenshot-backed prompt construction, prior-execution
summaries, context trimming, and compact strict-protocol recovery.
`phoneagent.agent` remains responsible for orchestration rather than prompt-history mechanics.

The canonical response is:

```xml
<answer>do(action="Tap", element=[500, 300])</answer>
```

The response must contain exactly one complete answer block at the end. Any text before it is
inert reasoning and is retained only for observability; assistant history is serialized back to
the model with the answer block alone. Unwrapped actions, JSON, Markdown fenced code, multiple
answer blocks, multiple calls, extra trailing text, malformed envelopes, and incomplete strings
are rejected. The runtime does not guess or repair an executable action.

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
Trajectory schema version remains `1.0` in PhoneAgent `v0.1.3`.

Each event contains its type, timestamp, message, payload, and optional top-level step. The
final state snapshot is included for convenience, but the event stream is authoritative for
execution history.

Trajectories may contain task text, model content, packages, timestamps, action parameters,
and evidence. They must be reviewed and redacted before publication.

## Trust boundaries

PhoneAgent `v0.1.3` does not claim independent task-level correctness:

- screen change does not prove that a coordinate target was semantically correct;
- secure or protected surfaces may be unobservable;
- the planning model currently reports full task completion through `finish(...)`;
- deterministic verification is only possible when Android state exposes sufficient evidence;
- real-device behavior varies by Android version, vendor ROM, launcher, permissions, and model
  provider.
