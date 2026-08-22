# PhoneAgent Model & Context Subsystem（模型与上下文子系统）

本文依据 [`src/phoneagent/model`](../../src/phoneagent/model) 和 [`config/prompts_zh.py`](../../src/phoneagent/config/prompts_zh.py)，说明 PhoneAgent 如何构造多模态上下文、调用 OpenAI-compatible 模型、消费流式响应，并把结果约束成一个可交给动作子系统的 `ModelResponse`。

## 1. 子系统位置

```text
ScreenObservation + AgentState + User Goal
                    ↓
              Context Builder
                    ↓
        OpenAI-compatible Model Client
                    ↓
     reasoning/content 流式收集与边界检测
                    ↓
               ModelResponse
                    ↓
          Action Subsystem.parse_action
```

这个子系统只保证模型响应具有一个终止动作调用的外层结构。动作字段是否合法、坐标是否越界，仍由 Action Protocol 的 `parse_action()` / `validate_action()` 判断。

## 2. 核心文件

| 文件 | 职责 |
| --- | --- |
| [`model/client.py`](../../src/phoneagent/model/client.py) | 配置、同步/异步流式调用、响应边界和指标 |
| [`model/context.py`](../../src/phoneagent/model/context.py) | 截图上下文、历史裁剪和协议恢复上下文 |
| [`config/prompts_zh.py`](../../src/phoneagent/config/prompts_zh.py) | 带当前日期的中文系统提示词 |
| [`config/messages.py`](../../src/phoneagent/config/messages.py) | CLI 展示用固定英文消息 |

## 3. `ModelConfig`

`ModelConfig` 描述一个 OpenAI-compatible endpoint：

| 字段 | 默认来源 |
| --- | --- |
| `base_url` | `BASE_URL`，默认本地 `http://localhost:8000/v1` |
| `api_key` | `API_KEY`，默认 `EMPTY` |
| `model_name` | `MODEL`，默认 `autoglm-phone-9b` |
| `max_tokens` | `MAX_TOKENS` |
| `temperature` | `TEMPERATURE` |
| `top_p` | `TOP_P` |
| `frequency_penalty` | `FREQUENCY_PENALTY` |
| `timeout` | `MODEL_TIMEOUT` |
| `max_retries` | `MODEL_RETRIES` |
| `retry_backoff` | `MODEL_RETRY_BACKOFF` |
| `extra_body` | 程序化供应商扩展参数 |
| `capture_usage` | 是否请求流式 usage |

初始化时会验证 endpoint、模型名、Token 上限、超时、重试、temperature 和 top_p 范围。

注意：CLI 为 `--max-tokens` 使用的默认值是 2048；直接构造 `ModelConfig()` 时类内默认值是 3000。两条入口最终都显式保存到同一个配置对象。

## 4. 消息格式

`MessageBuilder` 生成 OpenAI-compatible 消息：

- system：普通字符串；
- user：由可选 `image_url` data URL 和文本块组成；
- assistant：只保存动作字符串。

`remove_images_from_message()` 会在当前轮模型响应被接受后，从历史 user 消息中删除图片，只保留文本。这样历史轮次仍有 Screen Info 和动作结果，但不会无限携带旧图片。

## 5. 每轮上下文如何构造

`append_observation_message()` 将下面的信息放入一个截图支持的 user turn：

```text
User Goal
STRICT ACTION RECOVERY（若存在）
Previous Action Result（非首轮）
Saved Notes（最多最近 20 条）
Runtime Phase
Screen Info
当前截图
```

`Screen Info` 包含当前应用、包名、显示与图像尺寸、坐标系统、截图可用性、空白状态、摘要、系统面板状态、停滞次数，以及 Call_API 回调是否可用。

`Previous Action Result` 明确携带：

- 动作和 command success；
- runtime success 与 error_code；
- verification 证据；
- recovery 决策和结果；
- 当前停滞观测计数。

这使模型能够根据结构化执行反馈继续规划，而不是只看到自然语言“上一步失败”。

## 6. 上下文裁剪

`trim_context(messages, turns)` 保留：

```text
system message
+ 最近 turns 个完整 user/assistant 对
+ 当前尚未回答的 user message
```

不完整、角色顺序异常的历史不会被当作有效轮次保留。默认 `AgentConfig.context_turns=12`。

assistant 历史只写回 `response.action`，不会把 reasoning 或 raw content 重新灌入 Planner 上下文。这能降低错误推理不断自我强化的风险。

## 7. 系统提示词契约

`build_system_prompt()` 每次根据当前本地日期生成提示词，避免长期运行进程保留旧日期。提示词规定：

- content 只能包含一个 `do(...)` 或 `finish(...)`；
- reasoning_content 可以承载思考；
- 只能使用闭集动作和 `0..999` 坐标；
- 必须读取 Previous Action Result 的三层验证语义；
- 应用入口优先使用 Launch；
- 系统面板使用语义动作；
- 敏感最终步骤设置 sensitive，并接受运行时独立复核；
- `finish(success=True)` 只是待复核提议；
- 受保护页面必须 Take_over。

提示词是模型行为约束，不是安全边界本身。运行时仍会严格解析、确认、复核和验证。

## 8. `ModelResponse`

模型客户端输出：

```text
ModelResponse
├── thinking
├── action
├── raw_content
├── time_to_first_token
├── time_to_thinking_end
├── total_time
├── attempts
├── finish_reason
└── prompt/completion/total tokens
```

`truncated` 根据 `length`、`max_tokens` 或 `max_output_tokens` 等 finish_reason 计算。`to_assistant_message_content()` 只返回 action。

## 9. 外层响应协议

`ModelResponseParser` 从 content 中识别唯一一个位于响应末尾的平衡调用：

```text
[可选的惰性前缀 reasoning]
do(...)
```

或：

```text
finish(...)
```

它通过扫描引号、转义字符和括号深度确定调用边界，不执行文本。错误被分类为：

| error_code | 条件 |
| --- | --- |
| `missing_action` | 空内容或没有 do/finish |
| `legacy_action_envelope` | 出现旧 `<action>` 标签 |
| `incomplete_action` | 最后的调用没有闭合 |
| `multiple_actions` | 出现多个候选动作 |
| `trailing_content` | 动作之后还有正文 |
| `model_protocol_error` | 其他协议异常 |

外层 parser 允许动作前存在惰性文本以兼容部分供应商，但 Agent 回填历史时只保留动作。系统提示词仍要求普通 content 为纯动作。

## 10. 流式响应累积

同步与异步客户端共享 `_StreamResponseState`：

1. 记录请求开始时间；
2. 从 chunk 中读取 usage 和 finish_reason；
3. 分别收集 `reasoning_content` 与 `content`；
4. `StreamingBoundaryDetector` 跨 chunk、忽略大小写地检测 `do(` / `finish(`；
5. 记录 TTFT 和 reasoning 结束时间；
6. 流结束后统一调用 `ModelResponseParser`；
7. 构造相同语义的 `ModelResponse`。

如果 content 没有前缀 thinking，但供应商提供 reasoning_content，后者成为 `ModelResponse.thinking`。响应协议错误会保留 raw content、finish_reason 和 metrics，供轨迹与恢复诊断。

## 11. 同步与异步 transport

- `OpenAIModelClient` 使用 `OpenAI` 和同步 stream；
- `AsyncOpenAIModelClient` 使用 `AsyncOpenAI` 和 async stream；
- `ModelClient` 是同步实现的兼容别名；
- `PhoneAgent` 如果注入 async client 就优先使用异步路径，否则在线程中执行同步请求。

两种实现共享请求参数、usage fallback、响应累积、错误分类和重试语义。

HTTP client 设置 `trust_env=False`，不会自动继承系统代理环境。若供应商不支持 `stream_options.include_usage`，400/404/422 且错误文字表明该字段不支持时，会去掉该选项再请求一次。

## 12. transport 重试与取消

一次模型请求最多尝试 `max_retries + 1` 次，退避为：

```text
retry_backoff × 2^(attempt-1)
```

只有以下情况重试：

- HTTP 408、409、429；
- HTTP 5xx；
- timeout、connection、rate limit、internal server 类异常。

`ModelProtocolError` 和 `ModelRequestCancelled` 不属于 transport 重试，因为重复同一个网络请求不能可靠修复动作格式，取消也不能被覆盖。

同步 stream 使用请求级 watcher，在 cancel_event 触发时关闭 stream；异步 stream 由 Agent 取消任务并关闭。两条路径都在关键检查点抛出 `ModelRequestCancelled`。

已经发送的 ADB 命令不由模型取消机制回滚。

## 13. 两层协议恢复

PhoneAgent 对协议错误有两层处理，不能混为一谈。

### 13.1 同一步 ephemeral retry

首次外层协议或内部 Action Schema 失败时，`build_protocol_retry_context()` 深拷贝当前上下文，在相同截图 user turn 后追加严格格式要求：

- 不增加 Agent step；
- 不消费 recovery budget；
- 不把错误响应写入正式对话历史；
- 不派发设备命令；
- 默认最多 512 tokens；
- 默认允许一次 retry。

### 13.2 下一步 strict recovery

同一步重试仍失败后，`prepare_protocol_recovery()`：

- 删除没有 assistant 配对的 pending user turn；
- 把正式上下文压缩到最近 3 个完整轮次；
- 生成 `STRICT ACTION RECOVERY` 文本；
- 若错误文本包含供应商坐标标记，额外提示改用裸数值对；
- 将结构化失败交给 Recovery，通常选择 REPLAN。

下一轮会重新获取屏幕并将 strict recovery 指令加入新 user turn。

## 14. Semantic Review 的模型复用

任务完成复核和动作风险审核也通过 `_request_model_async()` 调用同一 transport，但使用全新的隔离上下文，并设置请求 `purpose`：

- `planning`；
- `task_completion`；
- `action_risk`。

这些上下文不继承 Planner 会话历史，并使用更小的 max_tokens 和独立协议重试。隔离上下文降低直接自我批准，但如果底层仍是同一个模型，它不是外部真值。

## 15. 与其他子系统连接

```text
Device Observation ──截图──> Context
AgentState ──阶段/上次结果──> Context
Context ──messages──> Model Client
Model Client ──ModelResponse.action──> Action Protocol
Protocol failure ──结构化错误──> Recovery
Model metrics ──事件──> Trajectory / Evaluation / Web UI
```

## 16. 当前限制

1. 当前 transport 直接面向 OpenAI-compatible Chat Completions，不是通用 provider plugin 层；
2. 完整图片仍以 data URL 进入请求，历史移除图片只能控制后续上下文；
3. action 边界依赖文本协议，模型仍可能输出格式错误；
4. usage 取决于供应商是否返回流式统计；
5. 协议重试会增加一次模型成本，但不会增加设备副作用；
6. 同一模型承担 Planner 和 Reviewer 时，判断错误可能相关。

## 17. 推荐阅读顺序与测试

1. `ModelConfig`、`ModelResponse`；
2. `MessageBuilder`；
3. `append_observation_message()` 和 `trim_context()`；
4. `ModelResponseParser`；
5. `StreamingBoundaryDetector` 与 `_StreamResponseState`；
6. 同步 `OpenAIModelClient`；
7. 异步 `AsyncOpenAIModelClient`；
8. 两层 protocol recovery；
9. 最后对照 Agent 的 `_request_step_model_response_async()`。

```bash
uv run pytest tests/test_model_context.py -q
uv run pytest tests/test_model_client.py -q
uv run pytest tests/test_action_protocol.py -q
```
