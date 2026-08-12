# PhoneAgent v0.2.0 Refactor

Status: release candidate complete (2026-08-12)
Target: 2026-08-28 release candidate
Scope: the final architecture-focused release before the project moves into evaluation,
real-device testing, and maintenance mode

## Outcome

PhoneAgent v0.2.0 should preserve the observable behavior of v0.1.4 while making the runtime
easier to test, explain, and change safely. The refactor is successful when the execution loop
has explicit stage boundaries, transport-specific code no longer owns shared model semantics,
action protocol and execution policy are independently testable, and the Web Console has a
small, auditable concurrency boundary.

This is a convergence release, not a rewrite or a feature expansion.

## Design constraints

The following contracts are frozen during the refactor:

- `PhoneAgent.run(...)`, `run_async(...)`, `step(...)`, and `step_async(...)` remain available.
- Existing public imports from `phoneagent`, `phoneagent.actions`, `phoneagent.model`, and
  `phoneagent.runtime` remain compatible.
- Every task still begins with a trusted observation.
- The strict terminal `do(...)` / `finish(...)` protocol remains unchanged.
- Model text is never evaluated as Python code.
- `Tap`, `Type`, `Swipe`, `Back`, `Double Tap`, and `Long Press` are never automatically replayed.
- Cancellation stops before the next device action but does not interrupt an already dispatched
  atomic ADB command.
- `AgentState.phase` remains the only live phase source and the trajectory event stream remains
  the authoritative execution history.
- Trajectory schema version remains `1.0` unless a separately documented migration is approved.
- CLI flags, environment names, local Web Console routes, and packaged entry points remain
  compatible.

## Non-goals

The refactor will not add a workflow framework, application-specific skills, a dynamic
application catalog, remote Web Console deployment, Android on-device execution, or a new model
action language. New actions and visual redesign work are deferred until the refactor is closed.

## Current pressure points

### Agent orchestration

`phoneagent.agent.PhoneAgent` currently owns run lifecycle, observation, model context, model
requests, action execution, verification, recovery, cancellation, state transitions, and event
recording. The async step implementation is the canonical path, but its large decision tree
makes local changes difficult to reason about.

The target is a thin step coordinator with explicit internal stage results. State and trajectory
updates must remain centralized so extracted services cannot create competing lifecycle sources.

### Model transport

The synchronous and asynchronous OpenAI-compatible clients repeat request, stream, usage,
retry, and error-normalization behavior. Transport mechanics may remain separate, but response
semantics, metrics normalization, retry classification, and protocol parsing should have one
implementation.

### Action boundary

Action parsing, validation, confirmation policy, coordinate conversion, and device execution
currently live in one module. They should become explicit protocol, policy, and execution
boundaries while the existing public imports remain stable.

### Web Console concurrency

`ConsoleRuntime` owns startup checks, one background agent task, prompt waits, cancellation,
event buffering, snapshots, and trajectory access. The refactor should make its single-task
concurrency contract explicit and test races deterministically rather than depending on short
wall-clock deadlines.

## Work sequence

### 1. Characterize v0.1.4 behavior

- Add focused tests for terminal paths, event ordering, cancellation checkpoints, verification
  fallback, and recovery-budget reset.
- Record the public API and configuration compatibility surface.
- Keep ordinary tests independent of a connected Android device or model provider.

### 2. Extract the step pipeline

- Introduce small internal result types for observation, planning, execution, and recovery.
- Extract pure decision helpers before moving side-effecting code.
- Keep state transitions and event creation owned by `PhoneAgent` until equivalence tests pass.
- Remove compatibility wrappers only when they are private and proven unused.

### 3. Normalize model and action boundaries

- Share model response, usage, retry, and error helpers across sync and async transports.
- Separate action protocol parsing and validation from confirmation policy and device dispatch.
- Preserve `phoneagent.actions` and `phoneagent.model` exports.

### 4. Bound Web Console concurrency

- Isolate startup state, active-task state, and prompt coordination.
- Make task identity checks explicit for background callbacks.
- Replace timing-sensitive tests with event-driven synchronization where possible.
- Split frontend code by API, state, timeline, and usage rendering without adding a build system.

### 5. Stabilize and measure

- Run lint, unit tests, build checks, and package installation checks.
- Add fault-injection seams for ADB timeout, disconnect, invalid screenshot, model cancellation,
  and foreground-package mismatch.
- Add a batch evaluation entry point around `task/tasks_v1.json` without changing agent behavior.
- Perform real-device regression runs and publish a model/device/result matrix.

## Acceptance criteria

The release candidate is ready when:

1. The frozen contracts above have regression tests.
2. `uv run ruff check .`, `uv run pytest -q`, and `uv build` pass from a clean checkout.
3. The normal test suite has no fixed sub-second sleep requirement for correctness.
4. Core protocol, state, verification, recovery, and trajectory modules retain at least 80%
   branch-aware coverage; boundary modules have explicit fault-path tests even when total ADB
   coverage remains lower.
5. Sync and async model transports pass the same behavior cases for response parsing, retry
   classification, usage normalization, cancellation outcome, and error metadata.
6. A saved v0.1.4 trajectory can still be opened by the v0.2.0 Web Console.
7. At least one real-device smoke suite passes for launch, tap, type, system-panel fallback,
   cancellation, and a multi-step task.
8. Architecture documentation explains the final module boundaries and the reasons behind the
   safety, verification, recovery, cancellation, and auditability choices.

## Schedule

- August 12–16: behavior characterization and Agent pipeline refactor.
- August 17–20: model, action, and Web Console boundaries.
- August 21–24: fault injection, packaging, and real-device regression.
- August 25–28: evaluation baseline, documentation, and release candidate.
- August 29–31: compatibility buffer and interview-oriented project review.

No new architecture work should enter the release after August 24 unless it fixes a demonstrated
correctness or safety problem.

The acceptance gates were completed on the refactor branch. The real-device environment,
retained failure, external annotations, and six-case result are recorded in
[`REAL_DEVICE_RESULT_v0.2.0.md`](REAL_DEVICE_RESULT_v0.2.0.md). Further August work is evaluation,
compatibility testing, documentation rehearsal, and demonstrated bug fixes rather than another
architecture version.
