# Contributing to PhoneAgent

Thank you for contributing.

## Development setup

```bash
git clone https://github.com/AuroraEchos/PhoneAgent.git
cd PhoneAgent
uv sync --extra dev
```

Run the local checks:

```bash
uv run pytest -q
uv run ruff check .
uv run python -m build
```

## Pull requests

Please keep changes focused and include tests for behavior changes. For runtime changes, describe:

1. the failure mode or capability being addressed;
2. the exact state/action transition affected;
3. the safety implications;
4. the trajectory evidence or regression test used to verify the change.

Avoid broad architectural rewrites in the same pull request as behavior fixes.

## Real-device reports

When reporting device-specific failures, include:

- Android version and device/vendor;
- ADB version;
- model endpoint and model name;
- the redacted trajectory JSON;
- whether the screen was protected, animated, or contained overlays;
- expected behavior and observed behavior.

Do not upload screenshots, trajectories, phone numbers, account identifiers, messages, tokens, or credentials without redaction.

## Code style

- Python 3.12+
- type annotations for public APIs
- deterministic, bounded recovery behavior
- no execution of model-generated code
- no hidden network/device side effects during package import

## Code of Conduct

Participation in this project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
