# PhoneAgent

[![CI](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AuroraEchos/PhoneAgent)](https://github.com/AuroraEchos/PhoneAgent/releases)
[![License](https://img.shields.io/github/license/AuroraEchos/PhoneAgent)](LICENSE)

[简体中文](README.md) | English

[Project site](https://auroraechos.github.io/PhoneAgent/) · [GitHub](https://github.com/AuroraEchos/PhoneAgent)

PhoneAgent is a vision-language Research Runtime / Evaluation Runtime for real Android
devices. It combines screenshot observation, model planning, a strict action protocol, ADB
execution, post-action verification, bounded recovery, and structured trajectories.

```text
Observe → Plan → Execute → Verify → Recover → Repeat
```

The project deliberately prioritizes reproducibility, auditable evidence, and explainable
failure behavior over broad workflow integrations or app-specific capabilities.

## Runtime properties

- Screenshot-grounded planning without requiring an accessibility tree.
- One complete terminal `do(...)` or `finish(...)` call is the only executable model-output
  region; preceding text is reasoning, while XML, multiple calls, trailing text, and malformed
  output are rejected.
- No heuristic repair of JSON, Markdown code fences, multiple actions, or incomplete strings.
- AST parsing, an action allow-list, parameter validation, and explicit confirmation for
  sensitive operations.
- Entry-app-first deterministic launch: after the first observation, an explicitly requested
  entry app is launched before visual planning; later `Launch` actions use the same lazy alias,
  installation, ADB, and foreground-package verification path.
- Separate command, observable-effect, and deterministic semantic evidence.
- Notification and Quick Settings semantic actions prefer `cmd statusbar`, fall back internally
  to normalized top-edge gestures when opening has no effect, and retain both attempts in the
  trajectory.
- Cancellation closes the active model stream and wakes bounded waits; already-dispatched ADB
  input remains atomic and no later action is issued.
- After confirmation and immediately before ADB dispatch, coordinate actions reobserve the
  screen. A changed target region or broad layout invalidates the old action with zero touch,
  retains the fresh observation for replanning, and records the conflict as a precondition event.
- Content-region fingerprints drive stagnation checks, and coordinate repetition applies only
  to actions that actually contain coordinates.
- Five recovery outcomes only: replan, reobserve, retry a safe action, request takeover, or
  abort.
- `AgentState.phase` as the only live phase source and `AgentEvent` as the audit-history
  source shared by callbacks and trajectories.

Only `Launch`, `Wait`, and `Home` may receive one automatic retry when the action is not
marked sensitive. Side-effecting or navigation actions such as `Tap`, `Type`, `Swipe`, and
`Back` are not replayed automatically.

The pre-action freshness guard is enabled by default for `Tap`, `Double Tap`, `Long Press`, and
`Swipe`. `--disable-pre-action-freshness` is available for diagnostics only.

## Requirements

- Ubuntu Linux
- Python 3.12+
- Android Platform Tools (`adb`)
- An Android device with USB debugging enabled
- A vision-language model endpoint compatible with OpenAI Chat Completions
- [ADB Keyboard](https://github.com/senzhk/ADBKeyBoard) for reliable multilingual and long
  text input (recommended)

Connect the device and approve the USB debugging prompt:

```bash
adb devices
```

A ready device is listed with the `device` state rather than `unauthorized`.

## Installation

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/AuroraEchos/PhoneAgent.git
cd PhoneAgent
uv sync --extra dev
cp .env.example .env
```

Configure a compatible model service in `.env`:

```dotenv
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL=autoglm-phone
API_KEY=YOUR_API_KEY
```

Zhipu BigModel is the recommended hosted service for the default `autoglm-phone` setup.

## Command line

```bash
uv run phoneagent --version
uv run phoneagent --help
uv run phoneagent --list-devices
uv run phoneagent --list-apps
```

Run one task:

```bash
uv run phoneagent "Open WeChat and search for the contact Zhang San"
```

Select a device explicitly:

```bash
uv run phoneagent \
  --device-id YOUR_DEVICE_ID \
  "Open the browser and search for PhoneAgent"
```

## Web Console

The local Web Console submits tasks, follows live `AgentEvent` updates, handles confirmation
and takeover prompts, and browses saved trajectories:

```bash
uv run phoneagent-web --open-browser
```

The default address is `http://127.0.0.1:8765`. Device and model preflight checks run once
per server session and are reused until the server stops. The console has no authentication,
so keep the default localhost binding unless you add your own protected reverse proxy.

See [webui/README.md](webui/README.md) for details.

## App launch aliases

PhoneAgent does not scan or cache an application catalog when a task starts. After the first
trusted observation, the runtime conservatively recognizes explicit entry wording such as
`open WeChat`, operation containers, and known mini-program containers. If the resolved package
is not already foreground, `Launch` becomes the first device action before visual planning.
Later model-issued `Launch` actions use the same built-in compatibility table in
`src/phoneagent/config/apps.py`, installation check, ADB launch, and foreground verification.
A failed initial launch is exposed to the model so it can choose a visible GUI path.

```bash
# All built-in human-readable aliases
uv run phoneagent --list-configured-apps

# Configured packages that are currently installed on the selected device
uv run phoneagent --list-apps
```

Add commonly used human-readable names to `APP_PACKAGES` when needed. The model may also emit an
exact package such as `com.example.app`; an installed application that is absent from the static
table is not discovered or injected into the model prompt automatically.

## Python API

```python
from phoneagent import PhoneAgent

agent = PhoneAgent()
result = agent.run("Open Settings and navigate to Wi-Fi")
print(result)
```

## Trajectories

Each run can create `runs/trajectory_<run-id>.json`. The event stream records phase changes,
model requests and responses, validated actions, execution evidence, verification, recovery,
and the final outcome. The final `AgentState` snapshot represents current/final state only;
the event stream is authoritative for execution history.

Trajectories may contain task text, model output, app or package names, timestamps, and action
parameters. Redact them before publication.

## Evaluation reports

An accepted `finish(success=True)` does not prove semantic correctness on the real device. After
external human or deterministic judgment, summarize trajectories with:

```bash
uv run phoneagent-eval runs \
  --annotations evaluation/annotations.json \
  --output evaluation/report.json
```

The report keeps runtime-reported and externally judged success rates separate and aggregates
steps, recoveries, error codes, model time, and Token usage. See
[`docs/EVALUATION.md`](docs/EVALUATION.md) for the evaluation and annotation contract, and
[`docs/REAL_DEVICE_REGRESSION.md`](docs/REAL_DEVICE_REGRESSION.md) for the release smoke matrix.
The first redacted v0.2.0 device result is in
[`docs/REAL_DEVICE_RESULT_v0.2.0.md`](docs/REAL_DEVICE_RESULT_v0.2.0.md).

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest -q
```

## Current boundaries

- ADB is required; PhoneAgent is not an on-device Android application.
- Observable screen change does not independently prove semantic correctness for coordinate
  actions.
- Full task completion is currently reported by the planning model.
- Protected or authentication-sensitive screens may require manual takeover.
- Human-readable `Launch` names are limited to the built-in compatibility aliases; unknown apps
  require an explicit Android package or an ordinary visual GUI path.
- Real-device behavior varies across Android versions, vendor ROMs, launchers, device
  permissions, and model providers.

## Acknowledgements

Early PhoneAgent development was inspired by
[zai-org/Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM). Thanks to the Zhipu AI team
for publishing Open-AutoGLM and advancing open mobile-agent research.

## License

Apache License 2.0
