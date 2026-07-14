# PhoneAgent

[简体中文](README.md) | English

[Project website](https://auroraechos.github.io/PhoneAgent/) · [GitHub](https://github.com/AuroraEchos/PhoneAgent) · [Release](https://github.com/AuroraEchos/PhoneAgent/releases/tag/v0.1.0)

PhoneAgent is a lightweight vision-language agent runtime for real Android devices. It captures the current screen through ADB, asks an OpenAI-compatible vision-language model for one constrained action, executes that action, verifies observable effects, and applies bounded recovery when necessary.

```text
Observe -> Plan -> Execute -> Verify -> Recover/Replan -> Repeat
```

The first public release, `v0.1.0`, focuses on a small, auditable, and testable execution loop rather than a large orchestration framework.

## Highlights

- Screenshot-driven VLM planning.
- AST/JSON-based safe action parsing; model text is never evaluated as Python.
- Dynamic discovery of launchable packages and confidence-aware app resolution.
- Deterministic package/activity launch for high-confidence pure-open tasks.
- Explicit distinction between command success, observable effects, and semantic action verification.
- Bounded recovery that never blindly replays `Tap`, `Type`, `Back`, `Swipe`, or other potentially side-effecting actions.
- Atomic JSON trajectory recording for observations, actions, verification, recovery, metrics, and state transitions.
- Manual takeover for protected, login, password, verification-code, and other sensitive screens.

## Scope and limitations

PhoneAgent is currently an **ADB-based research and engineering prototype**, not an on-device consumer product.

- For coordinate actions such as `Tap`, `Swipe`, and `Type`, a visual change proves only an observable effect. It does not prove that the model selected the semantically correct UI target.
- Overall task completion is currently self-reported by the planning model through `finish(...)`; there is no independent task judge yet.
- Screens protected by DRM, `FLAG_SECURE`, or vendor restrictions may not be observable. PhoneAgent refuses to guess coordinates on an untrusted blank screen.
- Launcher search fallback is vendor-dependent and is accepted only when a real foreground or visual change is observed.
- On-device deployment still requires an Android application built around `AccessibilityService`, `MediaProjection`, foreground services, explicit user controls, and privacy safeguards.

See [Architecture](docs/ARCHITECTURE.md) for the implemented execution path and [v0.1.0 Release Notes](RELEASE_NOTES_v0.1.0.md) for the first public release. See [GitHub Public Release Guide](docs/GITHUB_PUBLISH_GUIDE.md) for repository publication steps.

## Requirements

- Linux (primarily developed and tested on Ubuntu)
- Python 3.12+
- Android Platform Tools / `adb`
- An Android device with USB debugging enabled
- An image-capable model exposed through an OpenAI-compatible Chat Completions API
- [ADB Keyboard](https://github.com/senzhk/ADBKeyBoard) is recommended for robust CJK and special-character input

## Installation

```bash
git clone https://github.com/AuroraEchos/PhoneAgent.git
cd PhoneAgent
uv sync --extra dev
cp .env.example .env
```

Configure the model endpoint:

```dotenv
PHONE_AGENT_BASE_URL=http://localhost:8000/v1
PHONE_AGENT_MODEL=your-vision-language-model
PHONE_AGENT_API_KEY=EMPTY
PHONE_AGENT_DEVICE_ID=
```

## Usage

```bash
uv run phoneagent --list-devices
uv run phoneagent --list-apps
uv run phoneagent "打开设置"
uv run phoneagent "打开微信，然后搜索联系人张三"
```

For multiple devices:

```bash
uv run phoneagent --device-id emulator-5554 "open Chrome and search for PhoneAgent"
```

## Verification model

A verification record separates three facts:

```json
{
  "command_success": true,
  "observable_effect_verified": true,
  "semantic_effect_verified": null
}
```

- `command_success`: the Android/ADB execution layer accepted the command.
- `observable_effect_verified`: a foreground-app or visual change was observed.
- `semantic_effect_verified`: deterministic system state proves the action-level semantic result, for example the requested package is now foreground.

For ordinary coordinate actions, semantic verification is usually `null`.

## App aliases

When Android cannot expose a stable human-readable label, provide a JSON alias file:

```json
{
  "LeetCode": "com.lingkou.leetcode",
  "Camera": "com.example.camera"
}
```

or:

```json
{
  "com.lingkou.leetcode": ["LeetCode", "力扣"]
}
```

```bash
uv run phoneagent --app-aliases-file app_aliases.json "open LeetCode"
```

## Programmatic API

```python
from phoneagent import AgentConfig, PhoneAgent, RecoveryConfig, VerificationConfig

agent = PhoneAgent(
    agent_config=AgentConfig(
        verification=VerificationConfig(enabled=True),
        recovery=RecoveryConfig(
            enabled=True,
            allow_backtrack=False,
            allow_home_reset=False,
        ),
    )
)

print(agent.run("open Settings and navigate to Wi-Fi"))
print(agent.state.last_verification)
print(agent.last_trajectory_path)
```

Importing `phoneagent` does not load `.env`, inspect devices, or initialize a model client. The console entry point explicitly loads local environment configuration before importing runtime modules.

## Development

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run python -m build
```

## Security

PhoneAgent can operate a real device and may trigger external side effects. Do not use it unsupervised for payments, transfers, destructive operations, sensitive messages, or other high-risk workflows.

See [SECURITY.md](SECURITY.md) for reporting guidance.

## License

Apache License 2.0. See [LICENSE](LICENSE).
