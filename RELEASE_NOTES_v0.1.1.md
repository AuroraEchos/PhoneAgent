# PhoneAgent v0.1.1

PhoneAgent `v0.1.1` is a small, backward-compatible release focused on a more practical
real-device debugging workflow. The core Agent loop and public Python API remain compatible
with `v0.1.0`.

## Highlights

- A new local Web Console can submit natural-language tasks without returning to a terminal.
- Device, ADB Keyboard, screenshot, and model API checks run once when the server starts and
  are reused while that server session remains alive.
- Live runtime events show observation, planning, structured actions, execution evidence,
  verification, recovery, and final status.
- Sensitive operations and manual-takeover requests can be answered in the browser.
- Saved `runs/trajectory_*.json` files can be searched, inspected, and downloaded from the
  console.
- The console is included in the wheel and is available through the `phoneagent-web` command.

## Website and documentation

- Refined the landing page layout, restrained visual style, interactive phone presentation,
  capability list, task examples, and architecture flow.
- Updated public descriptions to match the actual deterministic app routing, visual Agent
  loop, action verification, recovery, and trajectory behavior.
- Kept the evaluation harness on the path to `v0.2.0`, after the benchmark dataset is ready.

## Safety boundaries

- Model API checks and runtime requests use an HTTP client that does not inherit ambient
  proxy environment variables, avoiding accidental routing through unrelated local proxies.
- The Web Console binds to `127.0.0.1` by default and has no built-in remote authentication.
- Cross-origin control requests are rejected and browser responses use restrictive security
  headers.
- Trajectory reads are constrained to validated trajectory filenames under the configured
  run directory.
- The console does not change the trajectory format; schema version remains `1.0`.

## Upgrade and start

```bash
git pull
uv sync --extra dev
uv run phoneagent --version
uv run phoneagent-web --open-browser
```

The default console address is `http://127.0.0.1:8765`.

## Known limitations

- Coordinate actions are still verified primarily through observable UI change rather than
  independent semantic correctness.
- Overall task completion is currently reported by the planning model.
- Protected or authentication-sensitive screens may require manual takeover.
- Real-device behavior varies by Android version, vendor ROM, Launcher, USB authorization,
  ADB Keyboard availability, and the selected vision-language model.
