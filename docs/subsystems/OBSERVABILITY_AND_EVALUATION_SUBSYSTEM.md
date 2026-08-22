# PhoneAgent Observability & Evaluation Subsystem（可观测性与评估子系统）

本文依据 [`runtime/events.py`](../../src/phoneagent/runtime/events.py)、[`runtime/trajectory.py`](../../src/phoneagent/runtime/trajectory.py) 和 [`evaluation.py`](../../src/phoneagent/evaluation.py)，说明 PhoneAgent 如何把一次实时执行保存成可审计证据，并在不连接模型和设备的情况下做离线统计。

## 1. 整体证据链

```text
PhoneAgent 中发生状态变化或运行操作
                ↓
             AgentEvent
          ↙               ↘
TrajectoryRecorder      event_callback
          ↓               ↓
trajectory_*.json      Web Console
          ↓
phoneagent-eval + 外部 annotations
          ↓
evaluation report
```

AgentState 只保存最新工作状态；历史事实以 events 为权威。Web 实时展示与磁盘轨迹接收同一个 AgentEvent，避免两套历史的时间戳和 payload 漂移。

## 2. `AgentEvent`

事件结构为：

```text
type
message
payload
step（可选）
timestamp
```

timestamp 使用创建事件时的 Unix 时间。`to_dict()` 复制 payload，只有 step 非空时才输出顶层 step。

当前 `EventType`：

| 类别 | 事件 |
| --- | --- |
| 生命周期 | `start`、`phase_change`、`finish` |
| 观测与模型 | `observation`、`model_request`、`model_response`、`thinking`、`metrics` |
| 协议与动作 | `protocol_retry`、`action`、`precondition`、`execution` |
| 安全与验证 | `risk_review`、`verification`、`task_verification` |
| 恢复与异常 | `recovery`、`error` |

## 3. 唯一事件创建路径

`PhoneAgent._record_event()`：

1. 深拷贝 payload；
2. 若 payload 中有 step，把它提升为 AgentEvent 顶层 step；
3. 创建一个 AgentEvent；
4. 先交给 TrajectoryRecorder；
5. 再把同一个 event 实例发给 event_callback。

callback 修改其收到的内容不会反向修改 Agent 内部 action 或 transition 数据，因为事件 payload 在创建前已经与运行时对象隔离。callback 抛出异常也只记录日志，不中断 Agent。

## 4. 事件中的关键语义

### 4.1 模型请求 purpose

MODEL_REQUEST / MODEL_RESPONSE / METRICS 使用：

```text
planning · action_risk · task_completion
```

协议重试还记录 protocol_attempt、protocol_retry、是否被拒绝、finish_reason、truncated 和 Token/延迟。

### 4.2 Execution

EXECUTION 明确记录 action、`command_success`、`should_finish`、requires_confirmation、error_code、metadata，以及是否属于 recovery retry。

finish 没有设备命令，因此 command_success 为 null，而不是 True。

### 4.3 Precondition 与零触摸失败

Freshness、安全边界和语义完成失败会保留 `command_dispatched=False`。这对事故分析很重要：失败可能发生在设备副作用之前。

### 4.4 Recovery

一次恢复通常有两条：stage=`decision` 和 stage=`outcome`。Evaluation 只把 outcome 计为一次已执行恢复。

## 5. `TrajectoryRecorder`

每次 `_start_run()` 创建独立 recorder，核心字段包括：

```text
schema_version = "1.0"
run_id = UUID hex
task
started_at / finished_at / duration_seconds
success / final_message
event_count / events
state（保存时可选）
```

`mark_finished()` 只设置最终时间、runtime success 和消息。`state` 是结束时的便利快照，事件流仍是执行历史的权威来源。

### 5.1 JSON 安全化

`_json_safe()`：

- 保留 None、str、int、bool；
- 有限 float 原样保留；
- NaN 和正负无穷转换为 null；
- dict 键转字符串并递归处理；
- list/tuple/set 转列表；
- 其他对象使用 repr。

最终 `json.dumps(..., allow_nan=False)`，保证输出是标准 JSON。

### 5.2 原子保存

保存顺序：

```text
创建 output_dir
→ 写入 .trajectory_<run_id>.json.<uuid>.tmp
→ os.replace(temp, final)
```

最终文件名为 `trajectory_<run_id>.json`。进程不会逐段覆盖最终文件，从而降低中途读取半份 JSON 的风险。

`TrajectoryRecorder.add()` 是自定义 evaluator 事件的兼容入口；正常 Agent 事件走 `add_event()`。

## 6. 离线 Evaluation 输入

`phoneagent-eval` 只读取磁盘 JSON，不初始化模型或设备。

`discover_trajectory_paths()`：

- 文件路径直接加入；
- 目录只发现顶层 `trajectory_*.json`；
- 路径统一 expanduser/resolve；
- 去重并排序；
- 不存在的输入抛 FileNotFoundError。

`load_trajectory()` 最少要求顶层 JSON object、非空字符串 run_id、events 为 list。它不要求轨迹来自当前代码版本，因此能读取保持核心 schema 的旧运行。

## 7. 外部 Annotation

Annotation 文件可以直接是 run_id 映射，也可以包在 `runs` 下：

```json
{
  "runs": {
    "<run_id>": {
      "task_success": true,
      "domain": "设备与系统",
      "notes": "人工核验说明"
    }
  }
}
```

`task_success` 只能是 true、false 或 null。没有 annotation 时，报告中的 task_success 必须为 null。

## 8. 单条轨迹摘要

`summarize_trajectory()` 从事件流统计：

- 最大 step；
- model request 数量与 purpose；
- 模型总耗时；
- prompt/completion/total tokens；
- 动作类型计数；
- recovery outcome 数量；
- completion/risk verdict；
- error_code 频率；
- runtime success；
- 外部 task success 和 domain/notes。

Token 某字段只有在供应商至少返回一次时才输出数值，否则保持 null。如果没有 total_tokens 但存在 prompt 或 completion，使用二者和补出 total。

步骤数取 events 顶层 step 和 final state.current_step 中的最大值。

## 9. 聚合报告

`build_evaluation_report()`：

- 拒绝重复 run_id；
- 报告 annotation 中没有匹配轨迹的 run_id；
- 聚合 runtime success、外部 task success、耗时、步骤、模型请求、Token、恢复、审核 verdict 和错误码。

比例定义：

```text
runtime_success_rate = runtime 成功数 / 所有 runs
task_success_rate = 外部判定成功数 / 有外部判定的 runs
```

未人工判定的运行不进入 task_success_rate 分母。

## 10. Runtime Success 不等于 Task Success

报告 methodology 明确保存：

- runtime_success：运行时接受了成功 finish；
- task_success：独立人工或确定性 evaluator 的外部判断。

即使任务完成 Reviewer 返回 PASS，它也可能与 Planner 使用同一个模型，所以不能替代外部 benchmark 标签。这是评估子系统最重要的语义边界。

## 11. `phoneagent-eval` CLI

```bash
phoneagent-eval runs/
phoneagent-eval runs/ --annotations annotations.json
phoneagent-eval runs/ --annotations annotations.json --output reports/baseline.json
```

报告总是输出到 stdout；指定 `--output` 时再使用临时文件加 `os.replace()` 原子写入。文件、JSON 或 annotation 校验错误以 argparse exit code 2 退出。

## 12. 隐私与发布边界

轨迹可能包含用户任务原文、模型 raw content/reasoning、应用名和包名、Type 文本、Call_API instruction、Note、截图摘要、时间戳、动作坐标和审核结果。

当前 recorder 不做自动脱敏。公开 benchmark、Issue 或演示前必须人工检查和清理轨迹。截图 Base64 在 observation event 中不保存，但任务与模型文本仍可能包含敏感信息。

## 13. 当前限制

1. Schema version 仍为 1.0，没有自动迁移器；
2. recorder 在内存保存完整 events，长任务受 max steps/runtime 约束；
3. summary 是通用统计，不计算领域步骤正确率或轨迹最优性；
4. annotation 只校验 task_success 类型，不强制标注者、版本或一致性协议；
5. 模型 Token 和耗时取决于供应商是否返回指标；
6. runtime success 与 reviewer pass 都不是外部任务真值。

## 14. 阅读顺序与测试

1. `EventType`、`AgentEvent`；
2. Agent `_record_event()` 和各 `_record_*`；
3. `TrajectoryRecorder`；
4. `summarize_trajectory()`；
5. `build_evaluation_report()`；
6. annotation 和 CLI 输出路径；
7. Web Console 如何消费相同事件。

```bash
uv run pytest tests/test_trajectory.py -q
uv run pytest tests/test_evaluation.py -q
uv run pytest tests/test_runtime_core.py -q -k event
```
