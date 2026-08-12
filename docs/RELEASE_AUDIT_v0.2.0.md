# PhoneAgent v0.2.0 Release Audit

Audit date: 2026-08-12

This document maps every acceptance criterion in `REFACTOR_V0.2.0.md` to direct evidence. Raw
device trajectories remain local and ignored; the redacted matrix is published separately.

## Acceptance evidence

| Criterion | Evidence | Result |
| --- | --- | --- |
| Frozen contracts | `test_public_api.py`, protocol tests, Agent loop tests, runtime state/event tests, Web HTTP route tests, and clean-wheel entry-point checks cover the Python API, strict terminal protocol, cancellation checkpoints, event ownership, schema compatibility, CLI/Web surfaces, and packaged commands. | PASS |
| Lint, tests, build | `bash scripts/release_check.sh` passed from a clean worktree: Ruff, 161 tests plus 43 parametrized subtests, JavaScript syntax, sdist/wheel build, checksums, and clean wheel installation. | PASS |
| No fixed short sleep in normal tests | The test tree contains no `time.sleep(...)` or `asyncio.sleep(...)`. Web background tests wait on `Condition`, `Event`, and observable state transitions with timeout guards. | PASS |
| Core branch coverage | Branch-aware run: action protocol 93%, state 85%, verification 90%, recovery 80%, trajectory 89%; combined 88%. | PASS |
| Sync/async model parity | Shared response-state implementation plus tests for successful response parsing, provider content/usage normalization, retry classification, truncation error metadata, stream closure, and cancellation outcome. | PASS |
| v0.1.4 trajectory compatibility | The representative schema-1.0 trajectory test is read through the refactored `TrajectoryStore`; schema version remains 1.0. | PASS |
| Real-device matrix | Launch, Tap, Type, system-panel command and edge fallback, cancellation, and multi-step task passed on the recorded vivo Android 16 matrix. One exploratory failure remains in the report. | PASS |
| Architecture and rationale | `ARCHITECTURE.md`, `EVALUATION.md`, `REAL_DEVICE_REGRESSION.md`, `REAL_DEVICE_RESULT_v0.2.0.md`, and `INTERVIEW_GUIDE.md` explain module boundaries, trust, verification, recovery, cancellation, concurrency, and honest evaluation. | PASS |

## Fault evidence

The automated suite injects observation timeout, invalid screenshot stream, secure-screen marker,
ADB action disconnect, model truncation/cancellation, foreground-package mismatch, verification
fallback, and stale Web callbacks. The real-device session additionally found and fixed:

- a reasoning-first provider being rejected by an eight-token preflight probe;
- ADB Keyboard remaining selected after a completed Type task.

## Complexity evidence

Measured against the v0.1.4 tag:

| Boundary | v0.1.4 | v0.2.0 |
| --- | ---: | ---: |
| Agent `_execute_step_async` | 394 lines | 29-line coordinator |
| Action handler module | 760 lines | 369 lines plus pure protocol/policy modules |
| Largest model `_request_once` | 157 lines | 74 lines with shared response state |
| Web `app.js` | 1070 lines | 704 lines plus four native ES modules |

The purpose of these reductions is independently testable decision boundaries, not minimizing
total source lines. `PhoneAgent` intentionally remains the owner of live phase and trajectory
events so the refactor does not create competing lifecycle state.

## Release boundary

Package, citation, changelog, website, release notes, wheel metadata, and CLI all report `0.2.0`.
Creating the Git tag, pushing the branch, and publishing the GitHub Release are external release
operations and are not performed by this audit.
