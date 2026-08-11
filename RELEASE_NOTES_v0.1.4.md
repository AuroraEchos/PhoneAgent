# PhoneAgent v0.1.4

PhoneAgent `v0.1.4` improves task control, deterministic Android entry behavior, model-provider
compatibility, verification quality, and Web Console observability while retaining trajectory
schema `1.0`.

## Runtime and task control

- Added native `run_async(...)` and `step_async(...)` APIs while preserving the synchronous
  `run(...)` and `step(...)` entry points.
- Added cooperative cancellation for active model streams, retry backoff, observation waits,
  action verification, recovery, and explicit `Wait` actions.
- Added a Web Console stop action and distinct `cancelling` and `cancelled` task states.
- Already-dispatched ADB input remains atomic; cancellation prevents the next action rather than
  interrupting a device command halfway through.

## Deterministic Android actions

- After the first trusted observation, an explicitly requested entry application can become the
  first deterministic `Launch` action before visual planning.
- Entry inference is conservative, handles common launch/container phrasing and mini-program
  hosts, respects negation, and skips launch when the target package is already foreground.
- Added `OpenNotifications`, `OpenQuickSettings`, and `CloseSystemPanel` semantic actions.
- Panel opening prefers an allowlisted `cmd statusbar` command, verifies WindowManager panel
  visibility, and uses one normalized top-edge gesture only when the primary route fails.

## Model protocol and transport

- The executable region is now one complete terminal `do(...)` or `finish(...)` call. Optional
  text before it is retained as reasoning; XML envelopes, JSON, Markdown fences, multiple calls,
  trailing text, and incomplete output are rejected.
- Added common model-client boundaries plus a native async OpenAI-compatible implementation.
- Cancellation closes active streams, retry delays are interruptible, and provider truncation
  reasons remain attached to protocol errors.
- Streaming usage collection automatically retries without `stream_options` when a compatible
  provider does not support that option.

## Observation and verification

- Screenshot capture now has bounded retries, typed permission/decode/timeout failures, strict
  stream validation, optional PNG/JPEG/WebP encoding, and cached device-resolution fallback.
- Ordinary visual comparison excludes system chrome and stores an application-content hash for
  stagnation decisions.
- System-panel actions require panel-state evidence rather than ADB success or incidental visual
  movement alone.
- Coordinate-loop protection normalizes numeric values and applies only to actions with actual
  coordinate fields.

## Web Console

- Added expandable work-process details with a concise latest-progress summary.
- Added Token, model latency, and optional estimated-cost summaries for live and saved tasks.
- Added input/output price configuration through `INPUT_PRICE_PER_1M_TOKENS`,
  `OUTPUT_PRICE_PER_1M_TOKENS`, and `COST_CURRENCY`.
- Preserved one checked runtime per Web server session and the existing localhost-only default.

## Configuration migration

Runtime environment variables now use concise names without the `PHONE_AGENT_` prefix. Update
existing `.env` files, for example:

```dotenv
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL=autoglm-phone
API_KEY=YOUR_API_KEY
DEVICE_ID=
WEB_HOST=127.0.0.1
WEB_PORT=8765
```

The complete supported configuration is documented in `.env.example`.

## Validation

- Source compilation, Ruff, the complete automated suite, distribution builds, and clean-wheel
  CLI/Web entry-point checks pass.
- The `phoneagent` and `phoneagent-web` commands remain available.
- Trajectory schema version remains `1.0`.

## Upgrade

```bash
git pull
cp .env.example .env  # or migrate the existing variable names manually
uv sync --extra dev
uv run phoneagent --version
uv run phoneagent-web --open-browser
```
