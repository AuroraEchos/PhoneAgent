# PhoneAgent Recovery Subsystem（失败恢复子系统）

本文依据 [`runtime/recovery.py`](../../src/phoneagent/runtime/recovery.py) 与 Agent 的 `_perform_recovery_async()` 执行路径，说明 PhoneAgent 如何把结构化失败转换为有界、保守的恢复操作。

## 1. 设计目标

恢复不是“失败后再点一次”。对于 GUI Agent，盲目重放 Tap、Type、发送或支付可能产生重复副作用。

Recovery Subsystem 把策略限制为五种：

```text
REPLAN · REOBSERVE · RETRY_ACTION · TAKEOVER · ABORT
```

它负责选择策略；策略的实际执行由 PhoneAgent 编排层完成。

## 2. 数据模型

### 2.1 `RecoveryContext`

决策输入包含：

- error_code 和 message；
- 原动作；
- 连续失败次数；
- 重复动作次数；
- 当前和目标应用；
- VerificationResult。

当前策略主要按 error_code、动作类型和本地预算决策；其他字段保留为可审计上下文和未来扩展点。

### 2.2 `RecoveryDecision`

```text
strategy
reason
failure_key
attempt
terminal
metadata
```

`failure_key` 当前定义为：

```text
<error_code>:<action_name>
```

无动作时 action_name 为 `none`。

### 2.3 `RecoveryOutcome`

保存 decision、恢复操作自身是否成功、消息、error_code 和 metadata。Decision 是“准备怎么做”，Outcome 是“执行后发生了什么”，轨迹将二者分别记录。

## 3. 配置与预算

默认 `RecoveryConfig`：

```text
enabled=True
max_total_recoveries=8
max_attempts_per_failure=2
retry_delay_seconds=0.35
allow_safe_action_retry=True
allow_takeover=True
```

最大值为 0 时，对应预算检查不启用；负数无效。

每次 `decide()` 先增加：

- 当前 failure_key 的 attempt；
- 整个任务的 total_recoveries。

超过总预算或同类失败预算后选择 terminal ABORT。

`mark_success()` 只清空当前 failure episode 的 attempts，不清零整个任务已经消费的 total recovery budget。

## 4. 决策优先级

`RecoveryManager.decide()` 按顺序匹配。

### 4.1 Recovery 被禁用或预算耗尽

直接 ABORT，terminal=True。

### 4.2 用户取消

`user_cancelled` 永远 ABORT。恢复不能覆盖用户明确拒绝或取消。

### 4.3 不可重放错误

以下错误选择 REPLAN，而不是重放命令：

```text
invalid_action
app_not_found / app_not_installed
verification_inconclusive
api_callback_not_configured
empty_api_instruction / empty_note
pre_action_observation_changed
task_scope_violation
task_semantic_verification_failed
task_semantic_verification_inconclusive
```

这里的“non-retryable”表示原动作不可直接 retry，不代表任务必须终止。

### 4.4 保护屏或黑屏

`protected_or_blank_screen`：允许 takeover 时选择 TAKEOVER，否则 ABORT。

### 4.5 观测错误

以下错误选择 REOBSERVE：

```text
observation_failed
screenshot_unavailable
verification_observation_failed
device_unavailable
pre_action_observation_failed
```

### 4.6 模型协议错误

action parse、missing/incomplete/multiple/trailing、legacy envelope、输出截断等错误选择 REPLAN，并由 Model Context 提供紧凑 strict-action prompt。

### 4.7 前台应用不匹配

`verification_app_mismatch`：如果原动作满足安全重试条件，选择 RETRY_ACTION；否则 REOBSERVE。

### 4.8 无效果、命令失败和重复动作

```text
verification_no_effect
verification_home_failed
launch_command_failed
action_execution_failed
repeated_action_blocked
```

安全动作可首次 RETRY_ACTION。不能安全重试时：

- action_execution_failed / repeated_action_blocked → REOBSERVE；
- 其他 → REPLAN。

未匹配的错误默认 REPLAN，把结构化证据交回模型。

## 5. 什么动作可以自动重试

安全重试白名单严格为：

```text
Launch · Wait · Home
```

还必须同时满足：

- 是 `do` 动作；
- 这是该 failure_key 的第一次恢复尝试；
- `allow_safe_action_retry=True`；
- 没有 sensitive；
- 没有 requires_confirmation；
- risk_level 不是 high。

Tap、Type、Swipe、Back、Double Tap 和 Long Press 永远不在自动重放白名单。即使 Back 通常像导航动作，重复 Back 也可能离开目标流程，所以测试明确固定为不盲目重试。

## 6. 策略如何执行

`PhoneAgent._perform_recovery_async()` 先进入 RECOVERING，构造 RecoveryContext，调用 decide，并记录 stage=`decision` 的 RECOVERY 事件。

### 6.1 ABORT

构造失败 Outcome，error_code=`recovery_aborted`。它是终止决策，StepResult.finished=True。

### 6.2 REPLAN

不执行设备命令，直接产生成功 Outcome，转回 OBSERVING。下一步重新观测或复用 pending observation，再让模型给出新动作。

### 6.3 REOBSERVE

等待 recovery delay，重新调用设备 observe：

- 拒绝空白/保护截图；
- 记录 source=`recovery_reobserve`；
- 保存 pending observation；
- 成功后让下一轮规划使用该画面。

失败返回 `recovery_reobserve_failed`。当前实现中该 Outcome 本身不是自动 terminal，后续还受连续失败和恢复预算控制。

### 6.4 RETRY_ACTION

取得 pending observation，缺失时重新观测；转到 EXECUTING；再次调用 ActionHandler，并记录 recovery=True 的 execution。

命令失败时返回 `recovery_action_failed` 并把控制权交回模型。命令成功后必须再次走完整 Verification；只有 retry verification.passed 才设置 `action_recovered=True`。

### 6.5 TAKEOVER

转到 WAITING_USER，执行内部 `Take_over` 动作。用户完成后重新观测，保存 pending observation，并回到 OBSERVING。

回调或观测失败会把 decision 改为 terminal，并返回 `recovery_takeover_failed`。

## 7. Runtime precondition failure

并非所有失败都来自已经执行的 Action。模型协议、语义审核、Freshness 和初始观测也可能在命令发送前失败。

`_handle_runtime_failure_async()` 为这些情况构造：

```text
ActionResult(success=False, command not sent)
VerificationResult(policy=runtime_precondition, command_success=None)
```

然后仍通过同一个 RecoveryManager 决策。事件 metadata 可携带 `command_dispatched=False`，明确说明没有设备副作用。

## 8. 成功、连续失败和恢复计数

- action verification 通过时调用 `mark_success()`；
- REPLAN/REOBSERVE 等恢复 Outcome 成功时也结束当前 failure episode；
- 成功恢复不会清空 total recovery budget；
- AgentState.recovery_count 在写入 recovery outcome 时增加；
- 原动作未成功但零触摸恢复成功时，consecutive_failures 会清零；
- terminal decision 或达到 Agent 的连续失败上限会结束任务。

因此局部瞬时冲突不会无限累积，但任务仍被总步骤、运行时间、恢复总数和同类失败次数共同限制。

## 9. 没有隐式导航重置

当前策略没有独立的：

- 自动 Back；
- 重新 Launch；
- Home reset；
- 任意坐标修正。

这些做法会扩大隐藏状态空间。除了白名单的同动作 retry，新的导航路径应由模型在新观测后显式输出，并继续经过 Action、Freshness 和 Verification。

## 10. 事件和状态证据

一次恢复通常产生两条 RECOVERY 事件：

```text
stage=decision
stage=outcome
```

Evaluation 只统计 outcome 数量为实际恢复次数。AgentState.last_execution 同时保存 verification 和 recovery，下一轮模型会在 Previous Action Result 中看到这两部分。

## 11. 当前限制

1. failure_key 只由 error_code 和 action_name 构成，不区分页面或具体坐标；
2. RecoveryContext 的部分字段目前尚未参与策略分支；
3. REOBSERVE 失败后不会在同一调用内递归恢复，而是交给外层预算和下一步；
4. 安全重试白名单是静态的；
5. TAKEOVER 的完成由用户回调返回表示，仍需后置观测；
6. REPLAN 成功只表示已安全交回 Planner，不表示原任务已经恢复成功。

## 12. 阅读顺序与测试

1. Strategy、Config、Context、Decision、Outcome；
2. `RecoveryManager.decide()` 的分支顺序；
3. `_safe_to_retry()`；
4. Agent 的 `_perform_recovery_async()`；
5. REOBSERVE、RETRY_ACTION、TAKEOVER 执行函数；
6. `_handle_runtime_failure_async()`；
7. AgentState 的 failure/recovery 更新。

```bash
uv run pytest tests/test_recovery.py -q
uv run pytest tests/test_agent_loop.py -q -k 'recover or failure or retry'
uv run pytest tests/test_runtime_core.py -q
```
