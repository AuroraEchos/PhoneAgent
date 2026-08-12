# PhoneAgent Evaluation Guide

PhoneAgent keeps runtime completion and task correctness separate:

- `runtime_success` means the runtime accepted `finish(success=True)`.
- `task_success` means a human or deterministic external evaluator verified the requested
  outcome.

A screen change, successful ADB command, or model completion claim is not sufficient evidence of
task correctness. Published results should use `task_success_rate`; runtime success is useful as
a diagnostic metric only.

## 1. Select and materialize tasks

[`task/tasks_v1.json`](../task/tasks_v1.json) contains 90 Chinese Android task templates. Replace
placeholders such as `{name}` or `{target_app_name}` with controlled test data before execution.
Record the device, Android version, ROM, model, model endpoint, PhoneAgent commit, and any initial
device-state assumptions for the evaluation session.

Do not automatically execute all tasks against a personal device. The set contains actions that
create or modify contacts, calendar entries, files, messages, orders, and other external state.
Use a dedicated test device and account, review each task, and restore its initial state between
runs.

## 2. Run tasks and retain trajectories

Run one materialized instruction at a time through the CLI or Web Console. Keep the generated
`trajectory_*.json` files in a session-specific directory. Review and redact screenshots, task
text, contact details, packages, model content, and action parameters before sharing them.

## 3. Annotate task correctness

Create a JSON object keyed by trajectory `run_id`:

```json
{
  "runs": {
    "8f3a...": {
      "task_success": true,
      "domain": "设备与系统",
      "notes": "Wi-Fi was enabled and remained enabled after verification."
    },
    "3c19...": {
      "task_success": false,
      "domain": "设备与系统",
      "notes": "The runtime stopped on the network overview instead of the Wi-Fi page."
    }
  }
}
```

`task_success` must be `true`, `false`, or `null`. Omitted and `null` judgments do not enter the
task-success denominator.

## 4. Build the report

```bash
uv run phoneagent-eval runs/session_2026-08-25 \
  --annotations evaluation/session_2026-08-25.annotations.json \
  --output evaluation/session_2026-08-25.report.json
```

The report includes:

- runtime and externally judged success rates;
- duration and step counts;
- model requests, model latency, and provider-reported token usage;
- action and recovery counts;
- structured error-code frequencies;
- one auditable summary per trajectory.

The command reads only `trajectory_*.json` when given a directory. Output is written atomically.
It does not call a model, connect to ADB, mutate the device, or infer task correctness.

## Recommended baseline matrix

For the final project report, use at least:

| Dimension | Minimum evidence |
| --- | --- |
| PhoneAgent | exact commit and version |
| Device | model, resolution, Android version, ROM |
| Model | provider, model name, relevant generation settings |
| Tasks | selected template indices and frozen materialized instructions |
| Repetitions | one exploratory run plus repeated stable subset |
| Correctness | external `task_success` annotation with notes for failures |
| Reliability | protocol, ADB, verification, recovery, and cancellation failures |
| Efficiency | steps, duration, requests, Token usage, and estimated cost if configured |

Avoid comparing models from different initial device states or silently excluding failed runs.
