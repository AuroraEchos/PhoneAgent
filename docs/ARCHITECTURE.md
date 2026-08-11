# PhoneAgent Architecture

This document describes PhoneAgent `v0.1.4` as implemented in the repository. PhoneAgent is
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

`AgentState.start(...)`, `finish(...)`, and `cancel(...)` own their corresponding lifecycle
transitions; `finished` is derived from the terminal phase. `AgentState.transition(...)`
validates non-terminal changes and returns a payload without a timestamp or step. Historical
phase changes, model output, actions, verification, and recovery decisions exist only in the
trajectory event stream.

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
`APP_LAUNCH_TIMEOUT_SECONDS`. There is no application-catalog TTL, discovery pass,
prompt candidate limit, or app-context injection switch.

### Android device layer

- `phoneagent.adb` contains parameterized ADB command, connection, screenshot, and input
  primitives.
- `phoneagent.devices.android.AndroidDevice` exposes the device interface used by the runtime.
- Model coordinates use the normalized `[0, 999]` space and are converted to the active device
  resolution before execution.

### Entry-app-first deterministic launch

PhoneAgent does not enumerate or cache installed applications when a task starts. Every task
still begins with a trusted device observation. Before the first model request, the runtime
conservatively matches explicit launch wording and operation containers such as `打开微信`,
`在支付宝里`, or `微信小程序` against the static alias table. If the resolved package is not
already foreground, the runtime makes `Launch` the first device action and records its source as
`runtime_initial_launch`. This avoids visually guessing launcher icons, labels, or folders and
also avoids spending a model request on a deterministic entry step.

If no explicit entry app is found, the target is already foreground, or the deterministic launch
fails, control remains with or returns to the normal screenshot-backed model loop. A failed
initial launch is not repeated automatically for `app_not_found` or `app_not_installed`; the
structured failure is exposed to the model so it may choose a visible GUI path.

For both a runtime-selected initial launch and a model-emitted
`do(action="Launch", app=...)`:

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

The canonical response may contain inert reasoning followed by one terminal action call:

```text
The visible target is the Settings icon, so open it directly.
do(action="Tap", element=[500, 300])
```

The response must end with exactly one complete `do(...)` or `finish(...)` call. Any text before
it is inert reasoning and is retained only for observability; assistant history is serialized
back to the model with the action call alone. XML envelopes, JSON, Markdown fenced code, multiple
calls, extra trailing text, and incomplete strings are rejected. The runtime does not guess or
repair an executable action.

Accepted action text is parsed with Python AST/literal handling and validated against the
action allow-list and parameter constraints. Model output is never evaluated or executed as
Python code. A protocol failure enters the existing bounded strict-action recovery path.

### Execution and confirmation

`ActionHandler` maps one validated action to Android operations. Supported operations include
launch, tap, type, swipe, back, home, double tap, long press, wait, note, API callback, user
interaction/takeover, notification/quick-settings panel control, and finish.

`OpenNotifications`, `OpenQuickSettings`, and `CloseSystemPanel` are semantic actions. Opening a
panel first uses the corresponding allowlisted `cmd statusbar` command. The runtime then observes
WindowManager panel visibility; a failed command or absent panel triggers one normalized top-left
or top-right swipe inside the execution layer. The fallback is invisible to model planning but
its primary/fallback attempts and final transport remain visible in trajectory metadata. Closing
uses `cmd statusbar collapse` without a blind Back fallback.

Actions marked sensitive, requiring confirmation, or detected as high-risk are paused at the
configured confirmation callback. Rejection is terminal for that action and is never
overridden by recovery.

Cancellation is propagated through the active model stream and bounded waits. A synchronous
stream has a request-local watcher that closes it when cancellation is requested; a native
async stream is cancelled and closed by the orchestration task. `Wait` uses the same
cancellation event and wakes immediately. Already-dispatched ADB input remains atomic: the
runtime lets that command return, then stops before issuing another device action.

### Verification semantics

Verification keeps three claims separate:

```text
command_success
observable_effect_verified
semantic_effect_verified
```

- Command success means the Android/ADB operation completed; `null` means no device command
  was attempted.
- Observable effect means a foreground-app or sufficient visual change was measured.
- Semantic effect requires deterministic evidence that the requested effect occurred.

For coordinate actions, visual change is not independent semantic proof. Status and navigation
bar regions are excluded from ordinary image comparison to reduce false positives. If an action
explicitly targets either system region, verification compares the full screen instead. The
runtime also stores a normalized application-content hash and uses it, rather than the full PNG
hash, for stagnant-screen and repeated-action decisions.

System-panel verification does not rely on ADB exit status or screenshot change alone. Each
observation records whether a recognized notification, quick-settings, or OEM control-center
window is focused or visibly surfaced. This avoids treating animation in the underlying app as
proof that a panel opened and also allows an already-closed `CloseSystemPanel` to pass
idempotently.

Repeated-coordinate detection applies only to actions that actually contain `element`, `start`,
or `end`. It deliberately ignores descriptions so rephrasing the same tap does not bypass loop
protection, while unrelated `Type` and `Launch` actions are not grouped as coordinate repeats.

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
Trajectory schema version remains `1.0` in PhoneAgent `v0.1.4`.

Each event contains its type, timestamp, message, payload, and optional top-level step. The
final state snapshot is included for convenience, but the event stream is authoritative for
execution history.

Trajectories may contain task text, model content, packages, timestamps, action parameters,
and evidence. They must be reviewed and redacted before publication.

## Trust boundaries

PhoneAgent `v0.1.4` does not claim independent task-level correctness:

- screen change does not prove that a coordinate target was semantically correct;
- secure or protected surfaces may be unobservable;
- the planning model currently reports full task completion through `finish(...)`;
- deterministic verification is only possible when Android state exposes sufficient evidence;
- real-device behavior varies by Android version, vendor ROM, launcher, permissions, and model
  provider.
