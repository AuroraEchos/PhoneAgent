# PhoneAgent Architecture

This document describes the execution path implemented by PhoneAgent `v0.1.1`.
It is intentionally limited to behavior present in the repository.

## Runtime overview

```text
CLI
  -> environment and device preflight
  -> PhoneAgent.run(task)
  -> app discovery and task initialization
  -> Observe
  -> Plan
  -> Parse and validate action
  -> Execute through ADB
  -> Verify post-action evidence
  -> Continue, recover, request takeover, or terminate
  -> persist trajectory
```

The runtime uses an explicit state machine. State transitions and significant events are
written to the trajectory so a failed run can be reconstructed without relying only on
terminal logs.

## Main components

### CLI and configuration

- `phoneagent.entrypoint` explicitly loads `.env`, then enters the CLI.
- `phoneagent.cli` validates arguments, checks the Android/ADB environment, constructs
  runtime configuration, and starts the agent.
- Importing `phoneagent` as a library does not load `.env`, connect to a device, or create
  a model client.

### Android device layer

- `phoneagent.adb` contains parameterized ADB command, connection, screenshot, and text
  input primitives.
- `phoneagent.devices.android.AndroidDevice` exposes the device-facing interface consumed
  by the runtime.
- Model coordinates use the normalized `[0, 999]` space and are converted to the current
  device resolution before execution.

### App discovery and deterministic routing

- `AppDiscovery` queries Launcher activities from the connected device.
- `AppCatalog` merges discovered packages with built-in and user-provided aliases.
- `AppResolver` returns candidates with confidence and ambiguity information.
- `LaunchAppCapability` prefers an explicit package/activity launch and falls back to a
  package-scoped launcher command when necessary.
- Launcher search is only treated as prepared when a foreground or visual change is
  actually observed.

Deterministic app routing is an optimization and reliability path. It does not replace the
visual loop for navigation inside an application.

### Model planning and action protocol

The planner receives the user goal, current screenshot, current application context,
prior execution evidence, recovery directives, and saved notes. The expected response is:

```xml
<think>brief reasoning</think>
<answer>do(action="Tap", element=[x, y])</answer>
```

Actions are parsed with Python AST/literal parsing or JSON parsing. Model output is never
executed as Python code. Parsed actions pass an allow-list and type/range validation before
reaching the executor.

### Execution

`ActionHandler` maps validated actions to Android operations. The runtime supports launch,
tap, text input, swipe, back, home, double tap, long press, wait, notes, API calls, user
interaction/takeover, and finish actions.

Potentially sensitive actions pass through the configured confirmation path. The runtime
does not silently reinterpret malformed actions.

### Verification semantics

Verification deliberately separates three claims:

```text
command_success
observable_effect_verified
semantic_effect_verified
```

- `command_success` means the Android/ADB command completed successfully.
- `observable_effect_verified` means a foreground-app change or sufficient post-action
  screen change was observed.
- `semantic_effect_verified` means deterministic state proves the intended semantic effect,
  such as the requested package being in the foreground.

For coordinate actions, observable change is not semantic proof. Status-bar and navigation
bar regions are cropped before visual comparison to reduce false positives from clocks and
system indicators.

Verification can return `passed`, `failed`, `inconclusive`, or `skipped`.

### Recovery

Recovery is bounded by per-failure-episode and total-task budgets. Successful progress ends
an active failure episode so unrelated later failures do not inherit its retry count.

Automatic action replay is restricted to a small set of idempotent operations. In
particular, the runtime does not blindly replay `Back`, `Tap`, `Type`, `Swipe`, `Double Tap`,
or `Long Press`.

Recovery may re-observe, replan, retry an allowed action, relaunch the target application,
request user takeover, or abort. More invasive backtracking/home-reset policies are disabled
by default.

### Trajectory

The trajectory recorder writes structured events through a temporary file followed by an
atomic replacement. The public `v0.1.1` trajectory schema is version `1.0`.

A trajectory can contain task text, model output, package/application names, timestamps,
action parameters, and execution evidence. It should be redacted before publication.

## Trust boundaries

PhoneAgent `v0.1.1` does not claim independent task-level correctness:

- visual change does not prove that a coordinate action was semantically correct;
- protected/secure screens may not be observable;
- the planner currently self-reports full task completion through `finish(...)`;
- deterministic verification is available only where Android state provides adequate
  evidence.

These boundaries are part of the runtime contract and should remain explicit as stronger
semantic verification is added.
