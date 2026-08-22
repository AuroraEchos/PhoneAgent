# PhoneAgent Subsystem Guide（子系统源码导读）

这个目录按照当前 PhoneAgent 源码职责拆分项目，并把各模块重新串成完整运行链路。它面向希望从代码层面理解项目的读者，不替代根目录 README 的安装和使用说明。

文档遵守三个原则：

1. 以当前代码实际行为为准，不把规划中的能力写成已经实现；
2. 明确输入、输出、错误和信任边界；
3. 始终区分命令成功、动作效果和任务成功。

## 1. 子系统总览

| 子系统 | 文档 | 核心源码 | 一句话职责 |
| --- | --- | --- | --- |
| 入口与配置 | [ENTRY_AND_CONFIGURATION_SUBSYSTEM.md](ENTRY_AND_CONFIGURATION_SUBSYSTEM.md) | `entrypoint.py`、`cli.py`、`config/` | 把环境、参数和预检结果变成运行配置 |
| Agent 编排与状态 | [AGENT_RUNTIME_AND_STATE_SUBSYSTEM.md](AGENT_RUNTIME_AND_STATE_SUBSYSTEM.md) | `agent.py`、`runtime/state.py` | 维护唯一状态机并串联整个任务循环 |
| 设备与观测 | [DEVICE_AND_OBSERVATION_SUBSYSTEM.md](DEVICE_AND_OBSERVATION_SUBSYSTEM.md) | `devices/`、`adb/` | 获得可信屏幕状态并执行受控 Android 操作 |
| 模型与上下文 | [MODEL_AND_CONTEXT_SUBSYSTEM.md](MODEL_AND_CONTEXT_SUBSYSTEM.md) | `model/`、`prompts_zh.py` | 构造多模态上下文并获得协议化模型响应 |
| 动作 | [ACTION_SUBSYSTEM.md](ACTION_SUBSYSTEM.md) | `actions/` | 解析、校验、确认和派发封闭动作集合 |
| 执行前新鲜度 | [FRESHNESS_SUBSYSTEM.md](FRESHNESS_SUBSYSTEM.md) | `runtime/freshness.py` | 阻止旧截图坐标在已变化界面上执行 |
| 动作效果验证 | [VERIFICATION_SUBSYSTEM.md](VERIFICATION_SUBSYSTEM.md) | `runtime/verification.py` | 根据动作类型判断命令和可观察效果 |
| 语义复核 | [SEMANTIC_REVIEW_SUBSYSTEM.md](SEMANTIC_REVIEW_SUBSYSTEM.md) | `runtime/semantic.py`、`actions/policy.py` | 复核风险动作与整项任务完成声明 |
| 失败恢复 | [RECOVERY_SUBSYSTEM.md](RECOVERY_SUBSYSTEM.md) | `runtime/recovery.py` | 在封闭策略和预算内恢复或终止 |
| 可观测性与评估 | [OBSERVABILITY_AND_EVALUATION_SUBSYSTEM.md](OBSERVABILITY_AND_EVALUATION_SUBSYSTEM.md) | events、trajectory、evaluation | 保存权威事件流并生成离线报告 |
| 本地 Web 控制台 | [WEB_CONSOLE_SUBSYSTEM.md](WEB_CONSOLE_SUBSYSTEM.md) | `webui/` | 将核心运行时适配为本地浏览器界面 |

## 2. 项目不是按目录一一对应子系统

源码中的包结构与职责边界并不完全相同：

- `runtime/` 不是单一子系统，内部 state、freshness、verification、semantic、recovery、trajectory 各有独立契约；
- `agent.py` 是编排者，不应该重复实现动作、验证或恢复算法；
- `adb/` 是设备子系统的低层实现，不是 Planner 可以直接访问的命令工具；
- `webui/` 是适配层，不维护第二套 Agent 逻辑；
- `evaluation.py` 只读轨迹，不连接设备或模型。

## 3. 完整架构

```text
┌─────────────────────────────────────────────────────────────┐
│                    CLI / Web Console                        │
│       参数、环境、预检、任务输入、确认与可视化               │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│               PhoneAgent + AgentState                       │
│        唯一状态机、步骤编排、边界、取消和事件创建             │
└──────────────┬───────────────────────────┬──────────────────┘
               ↓                           ↑
┌──────────────────────────┐   ┌──────────────────────────────┐
│ Device & Observation     │   │ Model & Context              │
│ 截图、前台包、面板状态     │ → │ 目标、截图、历史、模型响应     │
└──────────────────────────┘   └──────────────┬───────────────┘
                                              ↓
                               ┌──────────────────────────────┐
                               │ Action Subsystem             │
                               │ 兼容、解析、Schema、Policy    │
                               └──────────────┬───────────────┘
                                              ↓
                               ┌──────────────────────────────┐
                               │ Semantic Risk Review         │
                               │ ALLOW / CONFIRM / BLOCK      │
                               └──────────────┬───────────────┘
                                              ↓
                               ┌──────────────────────────────┐
                               │ Freshness Guard              │
                               │ 派发前重新观测与目标区域比较    │
                               └──────────────┬───────────────┘
                                              ↓
                               ┌──────────────────────────────┐
                               │ ActionHandler → AndroidDevice│
                               │ 真实 ADB 命令或受控回调         │
                               └──────────────┬───────────────┘
                                              ↓
                               ┌──────────────────────────────┐
                               │ Verification                 │
                               │ command / observable / semantic│
                               └──────────┬───────────┬───────┘
                                          │通过        │失败
                                          ↓            ↓
                                      下一轮 Observe  Recovery
                                                       ↓
                                 REPLAN / REOBSERVE / RETRY_ACTION
                                      / TAKEOVER / ABORT
```

所有阶段同时向旁路证据系统写事件：

```text
AgentEvent
├── TrajectoryRecorder → trajectory_*.json → phoneagent-eval
└── event_callback → Web Console timeline
```

## 4. 一轮正常执行时序

以一个普通 Tap 为例：

```text
1. Agent 进入 OBSERVING
2. AndroidDevice.observe 获取 Screenshot + window state
3. AgentState 更新 current app 和停滞计数
4. Context Builder 加入目标、上次结果、Screen Info 和截图
5. Model Client 返回唯一动作调用
6. Action Protocol 解析并校验 Tap
7. Action Policy 判断是否确认
8. Freshness 强制取得派发前新观测
9. 目标区域仍兼容，授权派发
10. ActionHandler 把 0..999 坐标映射为真实像素
11. AndroidDevice 发送 adb input tap
12. Verification 等待并取得 after observation
13. 检查前台应用或视觉变化
14. 通过后缓存 after observation
15. 下一步直接复用该可信观测，再次规划
```

## 5. 风险动作时序

```text
用户任务命中资金/商业、凭证/账户安全分类，或含显式否定边界
→ Planner 产生坐标动作
→ 确定性禁止边界检查
→ 隔离 Action Risk Review
   ├── ALLOW：继续
   ├── CONFIRM：等待人工确认
   ├── BLOCK：零触摸 task_scope_violation → REPLAN
   └── 无效/关闭：fail closed 到人工确认
→ 人工确认后重新做 Freshness
→ 只有界面仍兼容才执行
```

模型遗漏 `sensitive=True` 不能绕过原始任务分类或显式否定边界。普通通信、删除、预约等
任务若没有否定边界，不会只因任务文本进入该审核；一旦含有“不要发送/禁止删除”等边界，
即使坐标动作没有描述，也会进入截图风险审核。描述明确的冲突动作仍会先被确定性阻断。

## 6. 失败恢复时序

```text
解析 / 观测 / 前置条件 / 执行 / 验证失败
→ 产生稳定 error_code
→ RecoveryManager 构造 failure_key 并检查预算
→ 选择一种策略
   ├── REPLAN：不重放动作，交回模型
   ├── REOBSERVE：重新取得可信屏幕
   ├── RETRY_ACTION：只重试首次安全的 Launch/Wait/Home
   ├── TAKEOVER：等待人工操作后重新观测
   └── ABORT：终止任务
→ 记录 decision 和 outcome
→ 将 verification/recovery 写入 Previous Action Result
```

Tap、Type、Swipe、Back、Double Tap 和 Long Press 不会被恢复器盲目重放。

## 7. 任务完成时序

```text
Planner 输出 finish(success=True)
→ 这只是完成提议
→ Agent 强制获取最新可信截图
→ 从轨迹抽取最近 action/effect evidence
→ 构造不含 Planner 历史的隔离 completion context
→ Reviewer 返回 PASS / FAIL
   ├── PASS：接受 finish，进入 completed
   ├── FAIL：保存最新观测，REPLAN
   └── INCONCLUSIVE：不接受完成，REPLAN
```

运行时 Reviewer PASS 仍不等于 benchmark 的 `task_success`。外部评估必须通过 run_id annotation 提供真实任务判定。

## 8. 五个最重要的数据对象

| 对象 | 所属模块 | 作用 |
| --- | --- | --- |
| `ScreenObservation` | devices | 一次可信设备观测 |
| `ModelResponse` | model | 模型动作、thinking 和性能指标 |
| 动作 dict | actions | 经封闭 Schema 校验的执行意图 |
| `ActionResult` | actions | 命令级执行结果 |
| `VerificationResult` | runtime | 动作效果证据 |

外围对象：

- `AgentState`：当前工作状态；
- `StepResult`：一次 Agent step 的综合返回；
- `RecoveryDecision/Outcome`：恢复策略及执行结果；
- `SemanticReviewResult`：任务或风险语义判断；
- `AgentEvent`：跨持久化与 UI 的审计事件。

## 9. 必须始终区分的成功语义

```text
ADB command returned
        ↓
ActionResult.success / command_success
        ↓
Verification observable effect
        ↓
Action-level semantic effect（只在部分策略可证明）
        ↓
Runtime accepted task completion review
        ↓
External benchmark task_success
```

越往下，结论越强。上层成功不能自动替代下层证据。

## 10. 推荐阅读路线

### 10.1 你已经读到 Action，现在继续

如果从已经完成的 Action 文档出发：

1. [DEVICE_AND_OBSERVATION_SUBSYSTEM.md](DEVICE_AND_OBSERVATION_SUBSYSTEM.md)：理解 Handler 最终调用什么；
2. [MODEL_AND_CONTEXT_SUBSYSTEM.md](MODEL_AND_CONTEXT_SUBSYSTEM.md)：理解动作从哪里产生；
3. [AGENT_RUNTIME_AND_STATE_SUBSYSTEM.md](AGENT_RUNTIME_AND_STATE_SUBSYSTEM.md)：把上下游串成主循环；
4. [FRESHNESS_SUBSYSTEM.md](FRESHNESS_SUBSYSTEM.md)：理解点击之前的并发保护；
5. [VERIFICATION_SUBSYSTEM.md](VERIFICATION_SUBSYSTEM.md)：理解点击之后的证据；
6. [SEMANTIC_REVIEW_SUBSYSTEM.md](SEMANTIC_REVIEW_SUBSYSTEM.md)：理解任务和风险语义；
7. [RECOVERY_SUBSYSTEM.md](RECOVERY_SUBSYSTEM.md)：理解失败后如何继续；
8. [OBSERVABILITY_AND_EVALUATION_SUBSYSTEM.md](OBSERVABILITY_AND_EVALUATION_SUBSYSTEM.md)：理解证据如何保存和量化；
9. [ENTRY_AND_CONFIGURATION_SUBSYSTEM.md](ENTRY_AND_CONFIGURATION_SUBSYSTEM.md)：回看程序如何被配置和启动；
10. [WEB_CONSOLE_SUBSYSTEM.md](WEB_CONSOLE_SUBSYSTEM.md)：最后看外部适配层。

### 10.2 从程序入口完整走一遍

另一条路线是：

```text
Entry & Config
→ Agent Runtime & State
→ Device & Observation
→ Model & Context
→ Action
→ Semantic Review
→ Freshness
→ Verification
→ Recovery
→ Observability & Evaluation
→ Web Console
```

第一条更适合你当前的代码阅读位置，第二条更适合完成一轮后重新建立全局视角。

## 11. 测试与文档对应关系

| 测试 | 主要覆盖 |
| --- | --- |
| `test_action_protocol.py` | 模型动作外层/内层协议 |
| `test_actions.py` | Action Policy、Handler、坐标和系统面板 |
| `test_screenshot.py` | 截图可信性与失败类型 |
| `test_apps.py` / `test_app_resolution.py` | 应用解析、安装检查和入口推断 |
| `test_model_client.py` / `test_model_context.py` | 流式模型、取消、usage、上下文 |
| `test_runtime_core.py` | 状态、事件、核心循环与协议重试 |
| `test_agent_loop.py` | 完整 Agent 路径和跨子系统集成 |
| `test_freshness.py` | 执行前图像兼容性 |
| `test_verification.py` | 动作专用效果策略 |
| `test_recovery.py` | 恢复安全白名单和 failure episode |
| `test_trajectory.py` / `test_evaluation.py` | 原子轨迹和离线统计 |
| `test_env.py` | 配置入口和预检 |
| `test_webui.py` | 线程隔离、HTTP、prompt 和轨迹浏览 |

完整验证：

```bash
uv run pytest -q
uv run ruff check .
```

## 12. 阅读时的统一问题模板

阅读每个子系统时，始终回答：

1. 它接收什么输入，输入是否可信？
2. 它返回什么结构化结果？
3. 它是否产生设备或外部副作用？
4. 失败发生时，设备命令是否已经发送？
5. 谁负责验证它的结果？
6. 谁决定重试、重规划或终止？
7. 哪些事件会成为轨迹证据？
8. 哪个测试固定了这个行为？

## 13. 文档维护规则

当代码发生以下变化时，应同步修改对应文档：

- 新增动作或字段：Action；
- 修改 Screenshot/ScreenObservation 或 ADB transport：Device；
- 修改模型协议、上下文或 retry：Model；
- 修改阶段和主调用顺序：Agent Runtime；
- 修改视觉阈值或动作适用范围：Freshness / Verification；
- 修改 Reviewer prompt/verdict：Semantic Review；
- 修改 error_code 映射或重试白名单：Recovery；
- 修改事件 payload 或 trajectory schema：Observability；
- 修改 CLI/env/default：Entry & Configuration；
- 修改 Web API、任务状态或轮询：Web Console。

最终应以源码和自动化测试为事实来源，文档用于解释这些事实，而不是反过来替代代码契约。
