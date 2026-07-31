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
- One terminal `<answer>...</answer>` is the only executable model-output region; preceding
  text is reasoning, while unwrapped actions and malformed output are rejected.
- No heuristic repair of JSON, Markdown code fences, multiple actions, or incomplete strings.
- AST parsing, an action allow-list, parameter validation, and explicit confirmation for
  sensitive operations.
- Lazy deterministic app launch: a model-issued `Launch` resolves a built-in alias or explicit
  package, checks installation, starts it through ADB, and verifies the foreground package.
- Separate command, observable-effect, and deterministic semantic evidence.
- Five recovery outcomes only: replan, reobserve, retry a safe action, request takeover, or
  abort.
- `AgentState.phase` as the only live phase source and `AgentEvent` as the audit-history
  source shared by callbacks and trajectories.

Only `Launch`, `Wait`, and `Home` may receive one automatic retry when the action is not
marked sensitive. Side-effecting or navigation actions such as `Tap`, `Type`, `Swipe`, and
`Back` are not replayed automatically.

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
PHONE_AGENT_BASE_URL=https://open.bigmodel.cn/api/paas/v4
PHONE_AGENT_MODEL=autoglm-phone
PHONE_AGENT_API_KEY=YOUR_API_KEY
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

PhoneAgent does not scan or cache an application catalog when a task starts. When the model
emits `Launch`, the runtime resolves the supplied name through the built-in compatibility table
in `src/phoneagent/config/apps.py`, or accepts an explicit Android package name. It then checks
that package on the selected device and launches it lazily.

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
