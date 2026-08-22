# PhoneAgent v0.2.1

PhoneAgent v0.2.1 closes the semantic-review, Web-security, and documentation-hardening work on
top of the v0.2.0 runtime before the project freezes its first repeatable evaluation baseline.

## Semantic trust boundaries

- Treat `finish(success=True)` as a proposal and verify it against a fresh screenshot in an
  isolated context that does not reuse planner conversation history. Failed or inconclusive
  reviews return evidence to bounded replanning.
- Classify financial/commercial and credential/account-security tasks from the original user
  instruction, then review their coordinate actions with screenshot-backed `ALLOW`, `CONFIRM`,
  and `BLOCK` outcomes.
- Make explicit negative boundaries such as "do not send" an independent review trigger, so an
  unlabeled coordinate action cannot bypass the user's stated limit.
- Reject clearly described boundary conflicts before device dispatch. Keep that deterministic
  check limited to coordinate actions and `Call_API`, excluding `finish`, `Note`, `Take_over`, and
  other terminal or message-only actions from text-based false positives.
- Fail closed to human confirmation when action-risk review is disabled, unavailable, or cannot
  produce a valid verdict.

## Web Console security

- Validate every request Host against the configured bind authority and parse POST Origin against
  that trusted authority.
- Require explicit opt-in for non-loopback binding and reject wildcard bind addresses.
- Add cross-origin isolation, restrictive permissions headers, bounded request handling, and
  task-generation isolation for delayed callbacks.

## Documentation and evaluation evidence

- Add an integrated source guide for eleven runtime subsystems and a deterministic documentation
  social-preview asset.
- Validate guide manifests, required assets, JavaScript syntax, and the complete static site in CI,
  Pages, and release workflows.
- Extend offline reports and the Web timeline with model-request purpose, task-verification, and
  action-risk verdict summaries while keeping runtime completion separate from externally judged
  task correctness.

## Compatibility

- Public Python imports, CLI and Web entry points, environment names, local HTTP routes, and
  trajectory schema `1.0` remain compatible with v0.2.0.
- The new `SemanticReviewConfig` is available through the public runtime and package APIs.

## Validation status

The automated release gate passes 216 tests and 55 subtests, Ruff, Python compilation, Web and
documentation JavaScript syntax checks, static-site validation for all 12 guide documents, package
build, and clean-wheel installation.

This patch does not claim a new external task-success benchmark or a refreshed device/model
matrix. The recorded v0.2.0 Android 16 smoke result remains the latest published real-device
evidence; the next project phase will freeze task instances, initial states, device/model coverage,
repetition counts, external annotations, and cost reporting.
