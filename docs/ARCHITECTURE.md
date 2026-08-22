# PhoneAgent Architecture

This document describes the current `v0.2.1` runtime: the `v0.2.0` refactor baseline plus isolated
semantic review and Web hardening. PhoneAgent is deliberately scoped as a Research Runtime /
Evaluation Runtime for real Android devices.

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

The public `PhoneAgent` owns state transitions and event creation. Its step coordinator delegates
to explicit observation, response-selection, action-acceptance, device-execution, and
verification/recovery stages. Extracted stages return typed internal results; they do not own a
second state machine or event stream.

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

The canonical response content contains one action call and nothing else:

```text
do(action="Tap", element=[500, 300])
```

Provider `reasoning_content` may be retained for observability, but ordinary response `content`
is action-only. The parser remains able to read legacy inert prefix text for client compatibility;
assistant history is always serialized back with the action call alone. XML envelopes, JSON,
Markdown fenced code, multiple calls, extra trailing text, and incomplete strings are rejected.
The runtime does not guess or repair an executable action.

Accepted action text is handled by the side-effect-free `phoneagent.actions.protocol` boundary.
It uses Python AST/literal handling and validates each action against a closed keyword schema.
Unknown fields, duplicate keywords, missing required fields, dynamic expressions, and invalid
values are rejected. Model output is never evaluated or executed as Python code.

The first outer-protocol or inner-schema failure receives one ephemeral retry against the same
screenshot and goal. The retry does not advance the Agent step, consume recovery budget, append
the rejected output to model history, or dispatch a device command; its completion is capped at
512 tokens by default. `protocol_retry` and rejected-response metrics preserve the wasted latency
and Token evidence. If that retry also fails, the runtime enters the existing bounded
strict-action recovery path on the next step.

Synchronous and asynchronous OpenAI-compatible transports have separate stream I/O and
cancellation mechanics but share one response accumulator. Reasoning/content collection, action
boundary detection, finish reasons, usage normalization, truncation diagnostics, and final
`ModelResponse` construction therefore have one implementation.

### Execution and confirmation

`phoneagent.actions.policy` owns side-effect-free confirmation and duration rules.
`ActionHandler` is the device-dispatch boundary for an already validated action. It still
validates injected programmatic actions defensively before execution. Supported operations include
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

The confirmation boundary does not trust the planner to set `sensitive=True`. The policy also
classifies the original user task, but the consequence classifier is intentionally limited to
financial/commercial and credential/account-security operations. Coordinate actions in those
tasks, plus coordinate actions under an explicit negative task boundary, receive an isolated
screenshot-backed risk review with `ALLOW`, `CONFIRM`, or `BLOCK` outcomes. `CONFIRM` and invalid
review output fail closed to the human callback. A deterministic match between a described
side-effect action and an explicit "do not send/submit" boundary returns a zero-touch
`task_scope_violation` before model review. This deterministic check is limited to coordinate
actions and `Call_API`; terminal and message-only actions such as `finish`, `Note`, and
`Take_over` are excluded. Disabling model risk review conservatively sends every otherwise
reviewable coordinate action to human confirmation.

### Pre-action visual concurrency guard

Coordinate actions are bound to the screenshot that produced them, but Android applications may
show an advertisement, modal, or layout update while the model is responding. After any required
human confirmation and immediately before dispatching `Tap`, `Double Tap`, `Long Press`, or
`Swipe`, the runtime obtains one fresh observation and applies optimistic concurrency control:

1. Foreground application, system-panel state, and display dimensions must remain compatible.
2. The image region around every action coordinate is compared with the planning screenshot.
3. A near-full-screen replacement is a conservative fallback signal; ordinary video, carousel,
   and feed motion cannot override an unchanged target region.
4. Small unrelated animation outside the target region does not invalidate the action.

An invalidated action is never sent to ADB and is not coordinate-adjusted heuristically. The
runtime records a `precondition` event with `command_dispatched=false`, stores the fresh
observation for the next planning step, and reports `pre_action_observation_changed`. A capture
failure reports `pre_action_observation_failed` and enters bounded reobservation. A successful
zero-touch replan closes that individual failure episode; total recoveries, steps, and runtime
still bound a continuously changing interface. This reduces, but cannot mathematically eliminate,
the residual interval between the final screenshot and the atomic ADB command.

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

### Whole-task completion review

`finish(success=True)` is a proposal, not a terminal fact. Before accepting it, the runtime takes
a fresh trusted observation and creates a new model context containing only the original goal,
the latest screenshot, compact action/effect evidence, and completion-review instructions. It
does not reuse planner conversation history. The reviewer may return pass or fail; invalid output,
transport failure, missing visual evidence, and an explicit failure are non-terminal structured
failures that return control to replanning. The accepted verdict is stored in a
`task_verification` event and in the terminal execution metadata.

This removes direct planner self-approval, but it is still a model-backed review, potentially
using the same configured model. It is therefore runtime safety evidence rather than independent
benchmark truth. External human or deterministic `task_success` annotation remains required.

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
Trajectory schema version remains `1.0` in PhoneAgent `v0.2.1`, so existing `v0.1.4` runs remain
readable.

Each event contains its type, timestamp, message, payload, and optional top-level step. Pre-action
checks additionally record capture age, target/global difference ratios, dispatch authorization,
and whether a command had been sent at the time of the event. The final state snapshot is included
for convenience, but the event stream is authoritative for execution history.

Trajectories may contain task text, model content, packages, timestamps, action parameters,
and evidence. They must be reviewed and redacted before publication.

### Offline evaluation

`phoneagent-eval` reads saved trajectories without initializing a model or device. It reports
runtime completion, steps, actions, recoveries, structured failures, latency, Token usage, model
request purposes, and task/risk review verdicts.
Runtime completion is deliberately not treated as task correctness. `task_success` enters a
report only through an external human or deterministic annotation keyed by trajectory `run_id`.

### Web Console task isolation

The Web Console reuses one checked agent and permits one active task. Every callback carries an
internal task-generation context, including callbacks reached through `asyncio.to_thread`.
Callbacks whose generation does not match the current task are ignored, and a terminal worker
finishes cleanup before the next task starts. This prevents delayed events, notes, or prompts
from an older task mutating the next task snapshot.

The HTTP boundary validates every request Host against the explicit bind host and validates POST
Origin as a parsed same-origin authority. Non-loopback binding requires an explicit
`--allow-remote` opt-in, and wildcard bindings are rejected. This prevents accidental exposure
and closes the Host-header trust gap, but it does not add authentication; any remote deployment
still requires an authenticated TLS reverse proxy.

## Trust boundaries

The current PhoneAgent runtime does not claim independent task-level correctness:

- screen change does not prove that a coordinate target was semantically correct;
- secure or protected surfaces may be unobservable;
- the planning model proposes completion through `finish(...)`, and the isolated reviewer can
  still be wrong or share the same model biases;
- deterministic verification is only possible when Android state exposes sufficient evidence;
- real-device behavior varies by Android version, vendor ROM, launcher, permissions, and model
  provider.
