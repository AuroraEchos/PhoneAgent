# PhoneAgent Agent Runtime & State Subsystem（运行时编排与状态机）

本文依据 [`src/phoneagent/agent.py`](../../src/phoneagent/agent.py)、[`runtime/state.py`](../../src/phoneagent/runtime/state.py) 和 [`runtime/events.py`](../../src/phoneagent/runtime/events.py)，说明 PhoneAgent 如何把设备、模型、动作、安全、验证、恢复和轨迹串成一个有界任务循环。

## 1. `PhoneAgent` 是唯一编排者

`PhoneAgent` 不重新实现其他模块的算法。它持有并协调：

```text
AndroidDevice
BaseModelClient / AsyncOpenAIModelClient
ActionHandler
ObservationFreshnessGuard
ActionVerifier
RecoveryManager
AgentState
TrajectoryRecorder
```

主循环只有一份状态源和一条事件流。各子系统返回结构化结果，`PhoneAgent` 决定调用顺序、状态转换和下一步去向。

## 2. 核心配置和结果

### 2.1 `AgentConfig`

主要配置分为：

- 任务边界：`max_steps`、`max_runtime_seconds`；
- 失败边界：`max_consecutive_failures`、`max_repeated_actions`；
- 观测：重试次数、间隔、fallback screenshot；
- 模型上下文：`system_prompt`、`context_turns`；
- 协议：同一步重试次数与 Token 上限；
- 设备：device_id、应用启动超时；
- 持久化：trajectory_dir、save_trajectory；
- 嵌套配置：Freshness、Verification、Recovery、SemanticReview。

配置在 `__post_init__()` 中拒绝不合理的负数、零值和空范围。

### 2.2 `StepResult`

每一步返回：

```text
success              本步最终是否被验证或恢复
finished             任务是否结束
action               本步动作
thinking             Planner 思考文本
message/error_code   本步结果
command_success      是否执行并成功发送设备命令
verification         最终验证证据
recovery             恢复决策与结果
phase                返回时的阶段
```

内部 `_SelectedResponse` 区分模型响应与运行时确定性 Launch；`_AcceptedAction` 绑定解析后的动作；`_RecoveryExecution` 汇总恢复动作、验证和新观测。

## 3. 任务生命周期

### 3.1 `run()` 与 `run_async()`

`run()` 是 `asyncio.run(run_async(...))` 的同步包装。`run_async()`：

1. 拒绝空任务；
2. `_start_run()` 初始化状态和轨迹；
3. 在 max_steps 内重复 `_execute_step_async()`；
4. 每轮前检查取消和总运行时间；
5. StepResult.finished 时结束；
6. 捕获 KeyboardInterrupt / CancelledError；
7. 超过步骤或时间上限时产生失败 finish；
8. `_finalize_run()` 恢复键盘、终结状态并保存轨迹。

### 3.2 单步 API

`step()` / `step_async()` 只执行一个 Observe–Plan–Execute–Verify 单元，便于测试、交互式控制和嵌入。首次调用必须提供 task；上次任务已经结束时，开始新任务也必须提供 task。

### 3.3 reset

`reset()` 清除上下文、步骤计数、pending observation、严格协议恢复、取消标志、状态、RecoveryManager 和轨迹对象，但不重新创建注入的设备或模型客户端。

## 4. 状态机

`AgentState.phase` 是唯一实时阶段源：

```text
IDLE
→ INITIALIZING
→ OBSERVING
→ PLANNING
→ EXECUTING
→ VERIFYING
→ OBSERVING ...
```

失败路径可以进入：

```text
RECOVERING → OBSERVING / EXECUTING / WAITING_USER
```

终态为：

```text
COMPLETED / FAILED / CANCELLED
```

`_ALLOWED_TRANSITIONS` 显式列出合法边，非法跨越抛出 `StateTransitionError`。普通 `transition()` 禁止进入终态；终态只能通过 `finish()` 或 `cancel()`，且终态之后不允许继续转换。

相同阶段的 transition 返回 `None`，因此不会产生重复 phase_change 事件。

## 5. `AgentState` 保存什么

它只保存当前工作状态，不保存第二份历史：

- goal、phase、current_step；
- 当前和目标应用；
- 最近观测；
- 最近完整动作签名和坐标签名；
- 连续重复动作、重复坐标和停滞屏幕次数；
- 最近执行、验证和恢复；
- 最近最多 100 条失败原因；
- 连续失败与恢复次数；
- 最终成功、消息和时间戳。

历史的权威来源是 Trajectory events，而不是 AgentState 中不断增长的列表。

### 5.1 观测更新

`update_observation()` 优先比较 `content_sha256`，没有时才比较完整 screenshot sha256。这样状态栏时钟等系统区域变化不会轻易重置停滞计数。

### 5.2 动作重复计数

Agent 维护两种签名：

- 完整动作签名：包含动作字段，但统一整数/浮点坐标；
- 坐标签名：只包含动作类型与 element/start/end，忽略 description、message 和风险字段。

因此模型不能通过改写“点击按钮”的描述绕过同一坐标重复检测。

## 6. 一步的真实分解

`_execute_step_async()` 严格按四个阶段函数运行：

```text
_acquire_step_observation_async
→ _prepare_step_context
→ _select_step_response_async
→ _accept_step_action_async
→ _execute_accepted_action_async
```

### 6.1 Acquire observation

每步先进入 OBSERVING。优先复用上一轮已经验证的新观测，否则调用设备 observe。不可用截图进入 `screenshot_unavailable`；空白或保护屏进入 `protected_or_blank_screen`，不会继续让模型猜坐标。

### 6.2 Prepare context

把目标、上次执行、Notes、状态、Screen Info 和截图加入模型上下文，然后按 context_turns 裁剪。若上一轮协议失败，加入一次 STRICT ACTION RECOVERY。

### 6.3 Select response

首步会保守调用 `infer_task_entry_app(goal)`。如果任务明确要求进入某应用且它不在前台，运行时直接合成一个 Launch `ModelResponse`，source 为 `runtime_initial_launch`，不消耗模型请求。

如果没有明确入口、已在目标应用，或已经不是首步，才请求模型。

### 6.4 Accept action

模型响应先通过外层协议和 Action Schema，同一步格式重试完成后再正式接受。接受时：

- 更新动作及重复签名；
- 记录 ACTION 事件；
- 从历史 user turn 移除截图；
- 只把纯动作写入 assistant 历史；
- 转到 EXECUTING。

## 7. 被接受动作的执行顺序

`_execute_accepted_action_async()` 是安全顺序的中心：

```text
成功 finish？──是──> 新截图 + 隔离任务完成复核
        ↓
确定性任务禁止边界检查
        ↓
后果性坐标任务？──是──> 隔离动作风险审核
        ↓
坐标动作人工确认
        ↓
坐标动作执行前 Freshness
        ↓
重复动作阻断
        ↓
ActionHandler.execute
        ↓
终止动作？──是──> StepResult.finished
        ↓ 否
执行后 Verification
        ↓
必要时 Recovery
```

确认在 Freshness 之前，因为等待用户时界面可能变化。风险 BLOCK 和 Freshness 失败都会记录 `command_dispatched=False`。

## 8. 执行、验证和恢复如何合并

非终止动作进入 `_evaluate_action_result_async()`：

1. `_verify_action_async()` 生成 VerificationResult；
2. verification.passed 为假时调用 RecoveryManager；
3. RETRY_ACTION 可能产生新的 execution 和 verification；
4. 用最终 verification 更新 AgentState；
5. 保存 recovery outcome；
6. 判断 recovery terminal 或连续失败上限；
7. 未结束则回到 OBSERVING。

如果恢复成功但原动作仍未被验证，例如 REPLAN 或 REOBSERVE，StepResult.success 仍可为 False，但连续失败 episode 会清零，让下一轮拥有新的局部失败预算。

## 9. 观测缓存

执行后验证通常已经取得一张可信 after screenshot。Agent 将其放入 `_pending_observation`，下一步 `_next_observation_async()` 直接复用并记录 source=`verification_cache`，避免无必要重复截图。

以下路径也可能写入 pending observation：

- Freshness 发现界面变化后的当前截图；
- 任务完成复核失败时的最新截图；
- REOBSERVE；
- TAKEOVER 后的新截图；
- 安全动作 retry 的验证截图。

“缓存”只复用已经在运行时明确取得的最新观测，不是长期 TTL 缓存。

## 10. 初始应用启动

`infer_task_entry_app()` 只在任务具有明确证据时选择应用：

- 打开/启动/进入等动词；
- “在微信里”这样的操作容器；
- 微信或支付宝小程序容器；
- 明确 Android package。

仅仅在任务中提到一个应用名不足以强制启动，否定语境也不会命中。目标已在前台时跳过 Launch。

初始 Launch 失败不会永久卡住确定性路径：下一步 Previous Action Result 会暴露 `app_not_found`、`app_not_installed` 或启动/验证错误，控制权回到模型。

## 11. 限制、取消与重复保护

### 11.1 三类全局界限

- `max_steps`：默认 100；
- `max_runtime_seconds`：默认 900，0 表示不启用该限制；
- `max_consecutive_failures`：默认 3，0 表示不启用。

Recovery 还有独立的总预算和每类失败预算。

### 11.2 重复动作

只有界面停滞，并且完整动作或坐标签名达到上限时才返回 `repeated_action_blocked`。Wait、Note、Interact 和 Take_over 被排除；没有坐标的 Type/Launch 等也不会错误地共享坐标签名。

### 11.3 协作式取消

`request_cancel()` 只在任务已开始且未终结时设置 Event。Agent 在观测、模型请求、审核、Freshness、执行后和恢复等安全检查点退出。

- Wait 可被 Event 立即唤醒；
- 同步模型 stream 由 watcher 关闭；
- 异步模型 task 被取消；
- 已经派发的单个 ADB 命令视为原子操作，等待它返回后不再发下一条。

## 12. 运行开始与结束

`_start_run()`：

- 清空上下文和瞬时缓存；
- reset RecoveryManager；
- 把原始任务交给 ActionHandler 的任务策略；
- 新建带 task 和 run_id 的 TrajectoryRecorder；
- 记录 INITIALIZING 和 START。

`_finalize_run()`：

- 尝试恢复原输入法；
- 根据 result 进入 completed、failed 或 cancelled；
- 标记 trajectory 完成；
- 记录 FINISH；
- 如果启用，原子保存包含最终 state snapshot 的轨迹。

## 13. 事件是跨层接口

`PhoneAgent._record_event()` 创建唯一 `AgentEvent`，先写入 trajectory，再把同一个对象交给 callback。payload 会深拷贝，callback 异常只记录日志，不破坏任务。

事件覆盖 start、phase、observation、model request/response、protocol retry、action、precondition、risk review、execution、verification、task verification、recovery、finish、error 和 metrics。

Web Console 通过 callback 实时展示这些事件；Evaluation 从保存后的相同事件流离线统计。

## 14. 当前限制

1. `agent.py` 仍是较大的编排模块，内部阶段已拆成函数但尚未拆成独立 coordinator 类；
2. pending observation 是单值缓存，不承担通用时间序列存储；
3. 运行边界能阻止无限循环，但不能保证模型在预算内找到正确计划；
4. 成功状态依赖当前 semantic completion review，仍不是 benchmark 的外部真值；
5. 取消无法撤销已经提交给 Android 的原子输入命令。

## 15. 推荐阅读顺序与测试

1. `AgentConfig`、`StepResult`；
2. `AgentPhase` 与 `_ALLOWED_TRANSITIONS`；
3. `AgentState` 的 update 方法；
4. `PhoneAgent.__init__()`；
5. `run_async()` 与 `_execute_step_async()`；
6. 五个单步阶段函数；
7. `_execute_accepted_action_async()`；
8. verification/recovery 合并路径；
9. 观测缓存、重复动作与取消；
10. `_start_run()`、`_finalize_run()` 和事件函数。

```bash
uv run pytest tests/test_runtime_core.py -q
uv run pytest tests/test_agent_loop.py -q
```
