# PhoneAgent Web Console Subsystem（本地 Web 控制台子系统）

本文依据 [`webui/runtime.py`](../../webui/runtime.py)、[`webui/server.py`](../../webui/server.py) 和 [`webui/static`](../../webui/static)，说明 Web Console 如何复用 PhoneAgent 核心运行时，并安全地把任务、事件、人工确认和轨迹暴露给本地浏览器。

## 1. 定位

Web Console 不是另一套 Agent：

```text
Browser
  ↓ HTTP JSON / polling
ConsoleHTTPServer
  ↓
ConsoleRuntime
  ↓ callbacks
PhoneAgent
  ↓
核心 Model / Action / Device / Runtime
```

它是本地调试和演示适配层。核心决策、验证、恢复和轨迹仍由 PhoneAgent 完成。

## 2. 进程结构

`phoneagent-web` 进入 `webui.server.main()`：

1. 解析 host、port、open-browser、allow-remote，并验证绑定边界；
2. 创建 `ConsoleRuntime(Path.cwd())`；
3. 创建标准库 `ThreadingHTTPServer`；
4. 启动一次 startup checks；
5. 可选打开浏览器；
6. `serve_forever()`；
7. 退出时取消运行任务、唤醒 prompt 并关闭 server。

默认绑定 `127.0.0.1:8765`。控制台没有认证，非 loopback 地址默认拒绝，必须显式设置
`--allow-remote` 或 `WEB_ALLOW_REMOTE=1`；`0.0.0.0` 和 `::` 通配地址始终拒绝。远程模式仍
必须绑定明确接口，并由外部认证与 TLS 反向代理保护。

## 3. ConsoleRuntime 配置

`_build_configs(project_root)` 显式加载项目 `.env`，构造 ModelConfig、AgentConfig 和绝对 trajectory directory。

Web 读取模型 endpoint、主要循环限制、device_id、应用启动超时、verification retries/threshold、recovery 预算、任务完成审核、动作风险审核和 trajectory dir。

Token 价格由 `INPUT_PRICE_PER_1M_TOKENS`、`OUTPUT_PRICE_PER_1M_TOKENS` 和 `COST_CURRENCY` 构建，只用于 UI 估算。价格必须是有限非负数。

## 4. Startup checks

服务器会检查：

```text
ADB executable
Android device
ADB Keyboard
visual screenshot
model API
```

ConsoleRuntime 复用 CLI 的 `check_system_requirements()` 与 `check_model_api()`，捕获 stdout，再拆成 UI check records。

设备和模型都通过且解析出 device_id 后，才创建一个 PhoneAgent，注入 confirmation、takeover、event 和 note callback。

同一服务器会复用这个已检查 Agent 执行后续任务。用户可以在没有活动任务时重新运行 checks，此时旧 Agent 被丢弃并重新创建。

## 5. 线程安全状态

ConsoleRuntime 使用：

- `threading.RLock`；
- 基于该锁的 `Condition`；
- startup check thread；
- 每个任务一个 daemon worker thread；
- `ContextVar` 保存当前 callback task_id。

共享状态分为 startup、task、pending_prompt、pricing、events 和 trajectory store。

公开 snapshot 返回 deep copy 后的 JSON-safe 数据，浏览器不能直接修改服务器内部状态。

## 6. 一次只允许一个任务

忙状态集合：

```text
running · waiting_user · cancelling
```

`start_task()`：

- 拒绝空任务；
- 最长 8000 字符；
- startup 必须 ready；
- 服务器不能 closing；
- 不允许已有忙任务；
- 为任务生成 UUID task_id；
- 启动 worker thread。

上一个任务可能已经进入终态但 worker 仍在做 finally cleanup。代码会先在锁外 join 这个线程，再在锁内创建新任务，避免两个任务世代的 callback 重叠并产生死锁。

## 7. 任务世代隔离

worker 开始时将 task_id 写入 `_callback_task_id`。PhoneAgent 通过 `asyncio.to_thread()` 调用 Handler 时会传播 context，因此人工确认、Note 和 AgentEvent callback 都能识别所属任务。

每个 callback 都检查 task_id 存在、当前 task.id 相同，并且对事件而言任务仍处于忙状态。

旧任务延迟到达的事件、Note 或 prompt 会被忽略，不能污染新任务。测试明确覆盖 stale callback 场景。

## 8. AgentEvent 到 Web 状态

`_on_agent_event()` 更新当前摘要：

| Agent event | Web task 字段 |
| --- | --- |
| phase_change | phase |
| observation | current_app |
| planning model_response | last_thinking |
| action | last_action |
| verification | last_verification |
| task_verification | last_task_verification |
| risk_review | last_risk_review |
| recovery | last_recovery、outcome 时增加 recoveries |

所有事件还会复制到 Web 自己带连续 sequence 的短期事件缓冲。最多保留 2000 条，溢出后保留最近 1500 条。

Web 的 sequence 只用于浏览器增量拉取，不替代 trajectory 的 run event stream。

## 9. 人工确认与接管

confirmation 和 takeover 都进入 `_wait_for_prompt()`：

```text
创建 pending_prompt
→ task.status=waiting_user
→ 记录 user_prompt
→ Condition.wait()
→ 浏览器 respond_prompt
→ 清除 prompt
→ 恢复 running
→ 记录 user_response
```

普通 confirmation 可以接受或拒绝。Takeover 只能在用户完成手机操作后接受继续，Web API 不允许用拒绝表示“接管完成”。

取消等待 prompt 的任务时，会设置 Agent cancel_event，并把 prompt response 置为 False、唤醒 Condition，使 worker 能退出。

## 10. 协作式取消

`cancel_task()`：

- 只允许忙任务；
- 重复取消直接返回当前状态；
- 调用 Agent.request_cancel；
- task 转为 cancelling；
- 记录请求时间和 web_task_cancel_requested；
- 如果正等待用户，立即唤醒 prompt。

最终 worker 根据 AgentState.phase 把任务标为 success、failed 或 cancelled，并保存 trajectory 文件名。

## 11. HTTP API

GET：

| 路径 | 功能 |
| --- | --- |
| `/api/state` | 当前完整 snapshot |
| `/api/events?after=N` | N 之后的增量事件，HTTP 路由当前每次最多返回 250 条 |
| `/api/trajectories` | 最近轨迹摘要 |
| `/api/trajectory?name=...` | 读取单份轨迹 |
| `/api/trajectory?...&download=1` | 下载轨迹 |
| `/` 与静态文件 | Web 前端 |

POST：

| 路径 | 功能 |
| --- | --- |
| `/api/tasks` | 提交任务 |
| `/api/tasks/cancel` | 取消任务 |
| `/api/checks` | 重新检查 |
| `/api/prompts/respond` | 回答确认或接管 prompt |

请求体必须是 `application/json`、顶层 object，且大小为 1 到 64 KiB。

## 12. HTTP 安全边界

所有请求都解析并验证 Host：主机必须属于服务器显式绑定的允许集合，端口必须等于真实监听
端口。所有 POST 进一步检查 Origin：没有 Origin 的非浏览器请求允许；有 Origin 时，经过
URL 解析后的 scheme、hostname 和 port 必须与已验证 Host 完全一致。这样不会再把任意请求
提供的 Host 当作同源依据。

响应添加：

- CSP：脚本、样式、图片和连接限制为 self/data；
- `X-Content-Type-Options: nosniff`；
- `X-Frame-Options: DENY`；
- `Referrer-Policy: no-referrer`；
- `Cross-Origin-Resource-Policy: same-origin`；
- `Cross-Origin-Opener-Policy: same-origin`；
- 禁用 camera、microphone、geolocation、payment、usb 的 `Permissions-Policy`；
- API `Cache-Control: no-store`。

这些措施和默认绑定拒绝降低浏览器侧风险，但不构成身份认证。控制台仍应保持 loopback 绑定。

## 13. 轨迹浏览安全

`TrajectoryStore` 只接受：

```text
trajectory_[A-Za-z0-9_-]+.json
```

并同时要求 `Path(filename).name == filename`、resolve 后父目录仍是配置 trajectory dir、文件真实存在。因此 `../` 等路径遍历和任意文件下载会被拒绝。

列表默认最多 50 条，硬上限 200。

## 14. 浏览器前端

前端没有框架，使用 ES modules：

| 文件 | 职责 |
| --- | --- |
| `api.js` | fetch JSON 与统一 HTTP 错误 |
| `state.js` | 客户端状态和任务/phase 中文标签 |
| `timeline.js` | 事件过滤、摘要和时间线 DOM |
| `usage.js` | Token、耗时和可选费用 SVG 图表 |
| `app.js` | 状态轮询、表单、prompt、历史和页面协调 |

浏览器约每 800 ms 拉取 snapshot，每 550 ms 按 sequence 拉取增量事件。时间线把审核 model response 标为“模型完成复核”，最新过程文本只选择 purpose=planning 的 response。

Usage 面板从 model_response.metrics 统计每次请求 Token、耗时和估算费用；缺失 usage 时保持不可用提示，不伪造数值。

## 15. 当前限制

1. 无认证、无 TLS，只适合受信任本机；
2. 使用轮询而非 SSE/WebSocket；
3. 一个服务器会话只有一个 PhoneAgent 和一个活动任务；
4. Web 短期事件缓冲不是完整持久历史；
5. 启动检查通过只证明设备/API 可用，不证明任务成功率；
6. 前端费用完全基于手工配置单价和供应商 usage；
7. Traceback 会出现在本地 Web error event，不应把控制台暴露到不可信网络。

## 16. 阅读顺序与测试

1. `_build_configs()`；
2. `ConsoleRuntime.__init__()` 和状态对象；
3. startup checks；
4. `start_task()` / `_run_task()`；
5. callback task generation isolation；
6. prompt 和 cancel；
7. snapshot/events；
8. `TrajectoryStore`；
9. HTTP routes 和安全 header；
10. 前端 state → API → timeline → usage → app。

```bash
uv run pytest tests/test_webui.py -q
uv run phoneagent-web --help
```
