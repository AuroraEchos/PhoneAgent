# PhoneAgent v0.2.0

PhoneAgent v0.2.0 is the final architecture-focused release before the project moves into
real-device evaluation, regression testing, and maintenance mode.

## Runtime convergence

- Replaced the large monolithic step decision tree with explicit observation, context,
  response-selection, action-acceptance, device-execution, and verification/recovery stages.
- Kept `AgentState.phase` as the single live phase source and the trajectory event stream as the
  authoritative execution history.
- Removed obsolete private synchronous wrappers; `run`, `run_async`, `step`, and `step_async`
  remain available and share the canonical async implementation.

## Trust boundaries

- Separated strict AST/literal action parsing and validation from confirmation policy and Android
  device dispatch.
- Preserved the single terminal `do(...)` / `finish(...)` action protocol and all bounded-recovery
  safety rules.
- Added injected screenshot-timeout and ADB-disconnect regressions, including proof that a failed
  coordinate action is not blindly replayed.
- Fixed retry exhaustion so typed screenshot decode, permission, and capture errors reach the
  Agent recovery policy instead of becoming an unrelated bare-reraise runtime error.

## Model and cancellation behavior

- Unified reasoning/content accumulation, action-boundary detection, finish reasons, usage
  normalization, truncation diagnostics, and response construction across sync and async
  OpenAI-compatible transports.
- Added parity tests for response semantics, retry classification, provider content shapes, and
  Token usage.

## Web Console

- Bound Agent events, notes, and prompts to the task generation that created them, preventing a
  delayed callback from an old task mutating the next task.
- Ensured a terminal worker finishes cleanup before another task starts.
- Split the dependency-free frontend into native ES modules for API access, state labels,
  timeline rendering, usage charts, and application coordination.

## Evaluation

- Added `phoneagent-eval` for offline, atomic JSON reports over saved trajectories.
- Reports explicitly distinguish runtime acceptance of `finish(success=True)` from externally
  judged task correctness.
- Added an evaluation guide covering controlled task materialization, human annotations,
  redaction, baseline matrices, and honest success-rate reporting.

## Compatibility

- Public Python imports, `phoneagent`, `phoneagent-web`, CLI flags, environment names, and local
  Web routes remain compatible with v0.1.4.
- Trajectory schema remains `1.0`, and v0.1.4 trajectories remain readable.

## Validation status

The unit, integration-style, fault-injection, Web HTTP, JavaScript syntax, lint, package build,
and clean-wheel checks are release gates. Real-device smoke and evaluation matrices must be
completed and recorded before creating the v0.2.0 tag.
