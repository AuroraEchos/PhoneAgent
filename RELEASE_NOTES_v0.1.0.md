# PhoneAgent v0.1.0

PhoneAgent `v0.1.0` is the first public release of a lightweight Android GUI Agent runtime.
The release focuses on a complete, auditable execution loop rather than framework breadth.

## Highlights

- Vision-language planning over live Android screenshots.
- Safe AST/JSON action parsing with allow-list and parameter validation.
- Dynamic Launcher activity discovery and deterministic package/activity launching.
- Explicit runtime state machine and structured execution events.
- Post-action verification that separates command execution, observable change, and
  deterministic semantic evidence.
- Conservative, bounded recovery that does not blindly replay non-idempotent actions such
  as `Back`, `Tap`, `Type`, or `Swipe`.
- Atomic JSON trajectory persistence for debugging and evaluation.
- Manual takeover support for protected, authentication, or otherwise unsafe screens.
- Standard `src/phoneagent` package layout and the `phoneagent` CLI.
- Unit and fake-device integration tests covering the critical runtime path.

## Reliability changes included in the release

- Launcher search fallback now fails when no real foreground or visual change is observed.
- Recovery counters are scoped to a continuous failure episode and reset after successful
  progress.
- Status-bar and navigation-bar changes are excluded from visual-difference verification.
- Verification-disabled mode no longer conflicts with deterministic pure-app launches.
- Importing the Python package no longer loads `.env` or initializes external resources.

## Validation performed

- Python source compilation.
- Automated test suite on the local release workspace.
- Fake-device/fake-model end-to-end Agent Loop test.
- Wheel and source distribution build.
- Installation and CLI version check from the built wheel.

Real-device behavior depends on Android version, vendor ROM, Launcher implementation,
connected-device permissions, ADB Keyboard availability, and the selected visual-language
model. Real-device regression testing should therefore continue after publication.

## Known limitations

- Ordinary coordinate actions are verified by observable change, not by independent
  semantic correctness.
- Overall task completion is currently self-reported by the planning model.
- DRM/`FLAG_SECURE` and other protected surfaces may be unavailable to screenshot capture.
- Dynamic discovery reliably obtains package/activity identifiers, but application display
  names may require user aliases on some devices.
- The runtime is ADB-driven and is not yet an on-device Android application.

## Upgrade notes

This is the first public version. The import path is:

```python
from phoneagent import PhoneAgent
```

The command-line entry point is:

```bash
phoneagent --version
phoneagent "打开设置"
```

Trajectory schema version: `1.0`.
