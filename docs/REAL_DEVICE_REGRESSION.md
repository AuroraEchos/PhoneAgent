# PhoneAgent Real-device Regression

This is the release gate that cannot be replaced by mocked tests. Run it on a dedicated Android
device and test account after the local lint, test, build, and clean-wheel gates pass.

## Session metadata

Record this before running tasks:

| Field | Value |
| --- | --- |
| Date and operator | |
| PhoneAgent commit | |
| Package version | |
| Device and resolution | |
| Android version and ROM | |
| ADB connection type | USB / TCP/IP |
| Model provider and model | |
| Relevant generation settings | |
| Initial device state | |

Do not record API keys, personal account details, unredacted contacts, or other secrets.

## Preflight

```bash
adb devices -l
uv run phoneagent --version
uv run phoneagent --list-devices
uv run phoneagent --list-apps --device-id DEVICE_ID
```

Start each case from the stated initial state. Save each run in its own session directory, and
inspect its event stream before marking the case passed. A runtime `finish(success=True)` alone
is not pass evidence.

## Smoke matrix

| Case | Controlled task and initial state | Required evidence | Result / trajectory |
| --- | --- | --- | --- |
| Launch | From Home, open Settings | Settings is foreground; launch verification passed | |
| Tap | Open Settings and enter a harmless visible submenu | Correct submenu is visible; no coordinate replay occurred | |
| Pre-action race | Plan a harmless Tap, then surface a modal before dispatch | `pre_action_observation_changed`; `command_dispatched=false`; zero Tap execution events | |
| Type | In a disposable text field, enter a unique non-sensitive marker | Exact marker is visible and no unintended submission occurred | |
| System panel | Open notifications or Quick Settings from a normal app | WindowManager or panel evidence confirms the panel; gesture fallback is recorded if used | |
| Cancellation | Start a multi-step harmless task, then cancel while planning or waiting | No later device action is dispatched; terminal phase and event are `cancelled` | |
| Multi-step | Use one reviewed, harmless task from `task/tasks_v1.json` | Human checks the final semantic outcome and annotates `task_success` | |

For a failed case, keep the trajectory, record the exact stage and structured error code, restore
the device state, and rerun only after the cause is understood. Do not silently remove failed
runs from the evaluation denominator.

## Result record

```text
commit:
device / Android / ROM:
model:
cases passed: __ / 7
failed case IDs and error codes:
redacted trajectory directory or artifact:
external reviewer / date:
release decision: PASS / BLOCKED
```

The release gate is blocked until all seven cases pass on at least one recorded device/model matrix.
Broader device coverage is evaluation evidence, not a prerequisite for the first release
candidate.
