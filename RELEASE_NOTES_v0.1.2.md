# PhoneAgent v0.1.2

PhoneAgent `v0.1.2` is a focused runtime-consolidation release. It explicitly positions the
project as a PhoneAgent Research Runtime / Evaluation Runtime and removes duplicated or
heuristic behavior without adding horizontal capabilities.

> **Corrected release — 2026-07-26:** The original `v0.1.2` artifacts rejected valid output
> produced by the recommended `autoglm-phone` service when a single action was preceded by
> plain reasoning text. They could also reject a completed `finish(...)` call when its quoted
> message contained literal line breaks. The release was rebuilt from a corrected commit and
> the original artifacts were replaced.

> **Multi-provider compatibility update — 2026-07-26:** A subsequent real-device run with an
> OpenAI-compatible multimodal provider exposed coordinates such as
> `element=[<point>250 126</point>]`. The corrected release now includes a narrow provider
> syntax adapter that canonicalizes explicit point markers and `{x, y}` coordinate objects
> before applying the existing strict action validation.

> **Answer-only protocol update — 2026-07-27:** Cross-provider testing showed that requiring
> both `<think>` and `<answer>` tags caused otherwise correct actions to be rejected when a model
> emitted an unmatched thinking tag. The response protocol now uses one terminal answer block as
> its only executable boundary; earlier thinking-envelope and unwrapped-action compatibility
> paths are no longer part of the protocol.

## Answer-only model protocol

- Require exactly one complete `<answer>...</answer>` block at the end of every model response.
- Treat all preceding text as inert reasoning that is recorded for observability but never
  parsed as an action. `<think>` no longer has any protocol meaning.
- Reject unwrapped `do(...)` and `finish(...)` responses, multiple answer blocks, empty answers,
  and any content after `</answer>`.
- Serialize assistant history with the answer block alone so later turns are not prompted to
  imitate the removed thinking-tag format.
- Preserve literal CR/LF characters inside quoted action values before applying the existing
  AST and literal-only validation.
- Continue to reject JSON actions, Markdown-fenced actions, multiple actions, executable
  expressions, unclosed strings, and incomplete calls.
- Replayed the three malformed-envelope responses from the failing Meituan trajectory: each now
  extracts and validates exactly the action inside its terminal answer block.
- Verified on a connected vivo Android device with the task `打开设置,找到无线网络界面`:
  PhoneAgent launched Settings, entered the WLAN page, parsed the multiline completion, and
  finished with `phase=completed` and zero recoveries.
- Reverified on 2026-07-27 with `glm-4.6v-flash`: all four raw responses used the answer-only
  format and produced no model-protocol errors. One four-coordinate bounding box was safely
  rejected and corrected by the model on the next turn; the task completed without changing any
  WLAN setting.

## Multi-provider coordinate compatibility

- Canonicalize explicit two-number coordinates from `<point>`, `<point_2d>`, and
  `<|point_start|>...<|point_end|>` markers when they are attached to `element`, `start`, or
  `end` action fields.
- Accept exact coordinate objects such as `element={"x":250,"y":126}` and normalize them to
  `[250,126]`.
- Keep unknown tags, bounding boxes, multiple points, non-numeric values, executable
  expressions, extra object keys, and coordinates outside `0..999` invalid. Bounding-box
  centers are never inferred.
- Preserve provider-marker text inside ordinary string values instead of rewriting it.
- Add coordinate-specific system-prompt and strict-recovery guidance so compatible models can
  correct their own output format.
- Replayed every model action from the failing trajectory successfully, then completed a
  low-risk real-device JD search-entry task with `phase=completed` and zero recoveries.

## Runtime consolidation

- App aliases, launcher discovery, query resolution, and pure-launch intent handling now live
  in `phoneagent.apps.catalog` alongside the bounded catalog cache.
- `phoneagent.apps.models` and `phoneagent.apps.launcher` retain their focused responsibilities.
- Package-level imports from `phoneagent.apps` remain stable. Code importing the removed
  internal modules directly must switch to `phoneagent.apps`.
- Model prompt construction, context trimming, app-context serialization, and strict-protocol
  recovery moved from the main loop to `phoneagent.model.context`.

## Strict model action protocol

- The canonical and required response is `<answer>one do(...) or finish(...) call</answer>`.
- Text before the answer is inert reasoning; the answer block is the only executable region.
- Unwrapped actions, JSON actions, Markdown code fences around actions, multiple answers,
  multiple actions, extra trailing output, malformed envelopes, and incomplete strings are
  rejected rather than repaired.
- Protocol violations enter bounded strict-action recovery and are never guessed into an
  executable action.

## Minimal state and recovery model

- `AgentState.phase` is the only live phase source.
- Phase changes and execution history are stored only as trajectory events; the independent
  `TaskStateMachine` history was removed.
- Callbacks and trajectories receive the same `AgentEvent` instance, preserving timestamp,
  top-level step, message, and payload.
- Recovery is limited to replan, reobserve, retry a safe action, takeover, or abort.
- Only non-sensitive `Launch`, `Wait`, and `Home` may be retried once. Other actions are not
  automatically replayed.

## Web Console and documentation

- The Web Console now reads the app-context budget from `AppCatalogConfig`.
- Live events use `AgentEvent.step`, and event-derived model/action/verification views remain
  visible after the final `AgentState` snapshot is received.
- The English README was rewritten and the Chinese README, website, architecture document,
  configuration guidance, tests, version metadata, and release automation were aligned with
  the current runtime.

## Compatibility

- Core package imports such as `from phoneagent.apps import AppCatalog, AppResolver` remain
  supported.
- Direct imports from removed internal app modules and `TaskStateMachine` are intentionally no
  longer supported.
- The CLI and `phoneagent-web` entry points remain available.
- Trajectory schema version remains `1.0`.

## Upgrade

```bash
git pull
uv sync --extra dev
uv run phoneagent --version
uv run phoneagent-web --open-browser
```

Evaluation-suite integration is intentionally deferred; downstream evaluation code should
adapt to this runtime contract rather than adding compatibility layers back into PhoneAgent.
