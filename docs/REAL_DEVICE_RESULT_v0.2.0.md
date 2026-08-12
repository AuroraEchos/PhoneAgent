# PhoneAgent v0.2.0 Real-device Result

Date: 2026-08-12

Audited commit: `be9c8cbfc63c8000cb188dcb5acab3e09c3816da`

Purpose: release smoke and failure discovery, not a general model benchmark

## Environment

| Dimension | Value |
| --- | --- |
| Device | vivo V2527A (vivo S50 Pro mini) |
| Display | 1216 × 2640, density 560 |
| Android / ROM | Android 16, PD2527_A_16.0.18.3.W10 |
| Connection | USB ADB |
| Model | mimo-v2.5 |
| API shape | OpenAI-compatible Chat Completions |
| PhoneAgent trajectory schema | 1.0 |

The device serial, API credentials, screenshots, raw model content, and raw trajectories are not
published. They remain in the ignored local `runs/v020-smoke` directory.

## Release smoke matrix

| Case | Result | External evidence |
| --- | --- | --- |
| Launch | PASS | `com.android.settings` was the foreground package; Launch received semantic verification. |
| Tap | PASS after one retained failure | The controlled rerun reached `VivoWifiSettingsActivity` with the WLAN title visible and no network or switch selected. |
| Type | PASS | The exact disposable marker was visible, no result was selected, and the original vivo input method was restored after the task. |
| System panel | PASS | `NotificationShade` was focused; both `cmd statusbar` and the internal top-left edge-gesture fallback received semantic panel verification. |
| Cancellation | PASS | Cancellation ended in phase `cancelled`; zero execution events occurred after the first model-request event. |
| Multi-step | PASS | The Agent executed Launch, two Swipes, and Tap; `OriginDeviceSettingsActivity` and the About phone title were independently confirmed. |

The first Tap attempt is intentionally retained. It used the wrong scroll direction, later
produced one malformed model response, and exhausted six steps after an unintended network-row
interaction. Its structured errors were `verification_no_effect`, `model_protocol_error`, and
`max_steps_reached`. The rerun began from a recorded Settings-home initial state and passed with
one Tap and no recovery.

## Offline report

Eight trajectories were collected because Tap and Type each include a diagnostic run and a
controlled rerun. The intentional cancellation trajectory is useful reliability evidence but is
not a task-correctness trial, so its external `task_success` annotation is `null`.

| Metric | Result |
| --- | ---: |
| Total trajectories | 8 |
| Runtime successes | 6 / 8 (75.0%) |
| Externally judged trajectories | 7 |
| Task successes | 6 / 7 (85.7%) |
| Average steps | 3.125 |
| Model requests | 23 |
| Provider-reported tokens | 75,752 |
| Recoveries | 3 |

Runtime and task success happen to move in the same direction in this small session, but they are
not interchangeable. Runtime success records whether the Agent accepted
`finish(success=True)`; task success comes from independent Activity, UI, WindowManager, input
method, and event-stream checks.

## Issues discovered by the device run

1. The eight-token model preflight probe rejected a healthy reasoning-first response because its
   final content was empty. The probe now accepts non-empty reasoning as endpoint evidence while
   still rejecting a truly empty choice.
2. A completed Type task left ADB Keyboard selected. The action boundary now captures the original
   input method on the first Type, keeps ADB Keyboard for any later Type actions in the same task,
   and restores the original method during task finalization.
3. The failed exploratory Tap demonstrates why failed trajectories remain in the denominator and
   why screen change is not treated as semantic target correctness.

This matrix satisfies the single-device release gate. It does not establish cross-device,
cross-ROM, or general task-suite performance; those belong to the broader evaluation phase.
