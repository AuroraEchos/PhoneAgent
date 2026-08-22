# PhoneAgent Semantic Review Subsystem（语义复核子系统）

本文依据 [`runtime/semantic.py`](../../src/phoneagent/runtime/semantic.py)、[`actions/policy.py`](../../src/phoneagent/actions/policy.py) 和 Agent 的审核调用路径，说明 PhoneAgent 如何复核高风险坐标动作与 Planner 的任务完成声明。

## 1. 为什么需要语义复核

确定性代码可以证明：

- 动作格式是否合法；
- 坐标是否在范围内；
- ADB 命令是否成功；
- 屏幕是否变化；
- 某些应用或系统面板状态是否匹配。

但它通常无法只靠通用规则回答：

- 这个坐标是不是“发送”按钮；
- 点击后是否会产生外部副作用；
- 当前页面是否已经完整满足用户目标。

Semantic Review 使用最新截图和隔离上下文补充这层判断，同时在不确定时 fail closed。

## 2. 两类审核

```text
Action Risk Review
用户目标 + 禁止边界 + 当前截图 + 拟执行坐标动作
→ ALLOW / CONFIRM / BLOCK

Task Completion Review
用户目标 + 最新截图 + 紧凑运行证据 + Planner 完成消息
→ PASS / FAIL
```

两者复用模型 transport 和严格 finish 协议，但不复用 Planner 对话历史。

## 3. 数据模型

### 3.1 `ReviewVerdict`

| Verdict | 用途 |
| --- | --- |
| `PASS` / `FAIL` | 任务完成复核 |
| `ALLOW` / `CONFIRM` / `BLOCK` | 动作风险复核 |
| `INCONCLUSIVE` | 无法得到合法或可信结论 |
| `SKIPPED` | 配置关闭了该复核 |

`SemanticReviewResult.passed` 对 PASS、ALLOW、SKIPPED 返回 True。这个属性只表示对应审核流程不要求失败处理；Agent 对 action-risk 的 SKIPPED 仍额外强制人工确认。

### 3.2 `SemanticReviewResult`

保存 verdict、message、purpose、原始 model_action、attempts、error_code、模型 metrics 和补充 metadata，可直接序列化进事件与 execution metadata。

### 3.3 配置

默认配置：

```text
completion_enabled=True
action_risk_enabled=True
completion_max_tokens=512
action_risk_max_tokens=384
protocol_retries=1
evidence_event_limit=20
```

Token 上限必须为正，协议重试不能为负，证据至少保留一条。

## 4. 确定性任务策略作为第一层

语义模型审核之前，Action Policy 先检查用户原始任务。

`task_risk_reasons()` 只分类高后果任务：

- financial/commercial：支付、转账、提现、购买、下单、贷款、投资交易等资金动作；
- credential/account security：密码、验证码、PIN、密钥、助记词、银行卡绑定和账户注销等凭证或账户安全动作。

普通系统设置、一般通信、普通文件删除、预约和其他可逆操作若没有显式否定边界，不会仅凭
任务文本进入独立视觉审核。它们仍受动作自身的 `sensitive` 标记、风险等级和敏感描述约束。

上述高后果任务中的 Tap、Double Tap、Long Press、Swipe 会调用视觉 risk review；含显式否定边界的任务也会独立触发同一审核。单纯打开支付宝或银行应用不等于授权支付或转账，因此也不会触发。

`task_has_negative_boundary()` 识别“不要发送”“停留在提交前”“do not pay”等显式边界。若坐标动作或 `Call_API` 的 description/message/instruction 等又明确包含敏感效果，`task_scope_violation_message()` 直接 BLOCK，不调用设备。

这层确定性规则故意窄：动作描述模糊时不会猜测其效果，但显式否定边界本身会把无描述坐标
动作送入截图审核。`finish`、`Note`、`Take_over` 等终止或纯消息动作不参与确定性边界匹配。

## 5. 隔离上下文

### 5.1 Completion context

`build_completion_review_context()` 只构造两条消息：

```text
system：独立任务完成复核规则
user：JSON payload + 最新截图
```

payload 包含：

- `user_goal`；
- `planner_completion_message`；
- `screen_info`；
- `recent_runtime_evidence`。

它不包含 Planner 历史 reasoning，也不把 Planner 声明当作事实。

### 5.2 Risk context

`build_action_risk_review_context()` 包含：

- 用户原始目标；
- 任务风险类别；
- 是否存在显式禁止边界；
- 完整拟执行动作；
- 当前 Screen Info；
- 当前截图。

审核器知道坐标使用 `0..999`，并被要求不确定时选择 CONFIRM。

## 6. 紧凑运行证据

`compact_runtime_evidence()` 只保留最近限定数量的：

```text
action · execution · verification · recovery · precondition
```

每条只抽取 action、command_success、verification status/policy/effect、error_code、recovery decision、freshness 等字段。

模型 reasoning、raw output 和其他无关 payload 不会进入完成复核上下文。默认最多最近 20 条相关事件。

## 7. 审核输出协议

### 7.1 完成复核

只允许：

```python
finish(success=True, message="充分证据")
finish(success=False, message="缺失或冲突证据")
```

返回 do 或无法通过 Action Parser 都无效。success 映射为 PASS/FAIL。

### 7.2 风险复核

仍使用安全的 finish 调用承载 verdict：

```python
finish(success=True, message="ALLOW: 原因")
finish(success=False, message="CONFIRM: 原因")
finish(success=False, message="BLOCK: 原因")
```

同时接受英文或中文冒号。前缀与 success 必须一致；例如 `success=True + BLOCK:` 会被拒绝。

## 8. 有界审核请求

`_request_semantic_review_async()`：

1. 记录带 purpose 的 MODEL_REQUEST；
2. 使用 `min(ModelConfig.max_tokens, review_max_tokens)`；
3. 调用同一模型 transport；
4. 使用对应 parser；
5. 保存 metrics 与带 purpose 的 MODEL_RESPONSE；
6. 格式失败时深拷贝原上下文，追加一次 finish-only 纠错指令；
7. 重试耗尽或 transport 失败时返回 INCONCLUSIVE。

审核协议重试不会执行设备动作，也不进入 Planner 正式上下文。

## 9. 任务完成复核流程

当 Planner 提出 `finish(success=True)`：

```text
进入 VERIFYING
→ 强制取得新观测，不使用 planning screenshot 代替
→ 拒绝不可用/空白截图
→ 压缩运行证据
→ 构造隔离 completion context
→ 请求 PASS/FAIL
```

PASS：

- 结束当前 failure episode；
- 转回 EXECUTING；
- 让 ActionHandler 构造 terminal ActionResult；
- 把 review 写入 `task_verification` 事件和 terminal execution metadata。

完成复核之后仍会经过通用策略入口，但 `finish` 已明确排除在确定性否定边界检查之外；
“已输入但未发送”这类成功说明不会因自身文字产生误阻断。

FAIL：

- 保存最新观测给下一轮；
- 返回 `task_semantic_verification_failed`；
- command_dispatched=False；
- Recovery 选择 REPLAN。

无法截图、格式无效或请求失败：

- 返回 `task_semantic_verification_inconclusive`；
- 不接受完成声明；
- 重新规划。

如果 completion review 被显式关闭，返回 SKIPPED，当前 Planner 的成功 finish 会被接受。该开关是诊断选项，会降低默认安全保证。

`finish(success=False)` 是 Planner 主动失败终止，不做成功复核。

## 10. 动作风险复核流程

高后果任务或含显式否定边界任务中的坐标动作：

```text
确定性禁止边界
→ risk review
→ ALLOW：继续
→ CONFIRM：人工确认
→ BLOCK：task_scope_violation，零触摸重新规划
→ INCONCLUSIVE：人工确认
→ SKIPPED：人工确认
```

风险审核使用产生动作的 planning observation。人工确认之后还会执行 Freshness，因此用户等待期间的界面变化不会直接沿用旧坐标。

如果 action-risk review 被关闭，代码明确返回 SKIPPED 和 `action_risk_review_disabled`，并 fail closed 到人工确认，而不是放行。

## 11. 事件与评估

请求目的记录为：

```text
planning · action_risk · task_completion
```

审核结果分别记录 `risk_review` 和 `task_verification` 事件。Web Console 只把 purpose=planning 的 model response 当作“最新思考”，审核输出单独展示。

离线 Evaluation 会统计请求 purpose 和 verdict 频率，但不会把 runtime completion review 当作 benchmark 真值。

## 12. 信任边界与限制

1. 隔离的是对话上下文，不一定是底层模型；同模型错误可能相关；
2. Reviewer 仍然可能误读截图或目标；
3. 正则风险分类只能覆盖已编码的常见中英文表达；
4. 视觉审核只针对高后果任务或含显式否定边界任务中的坐标动作，非坐标副作用仍依赖动作
   Schema、确定性策略和人工确认；
5. Completion PASS 是运行时安全证据，不是外部 task correctness；
6. 每次成功 finish 至少增加一次模型请求，受审核坐标动作也可能增加请求成本；
7. 人工确认只确认当前提示，不自动证明最终任务正确。

真实 benchmark 的 `task_success` 必须来自独立人工或确定性 evaluator annotation。

## 13. 阅读顺序与测试

1. `ReviewVerdict`、Config、Result；
2. 两个 system prompt；
3. 两个 context builder；
4. 两个 parser；
5. `compact_runtime_evidence()`；
6. Agent 的 `_request_semantic_review_async()`；
7. `_review_action_risk_async()`；
8. `_review_task_completion_async()`；
9. Action Policy 的任务风险函数。

```bash
uv run pytest tests/test_agent_loop.py -q -k 'risk or finish or semantic'
uv run pytest tests/test_runtime_core.py tests/test_actions.py -q
```
