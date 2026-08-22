# PhoneAgent Action Subsystem（动作子系统）

本文基于当前代码实现，系统说明 PhoneAgent 的动作子系统：模型输出如何变成一个受约束的动作，动作如何经过安全策略，最终如何被派发到 Android 设备，以及执行结果如何返回 Agent 主循环。

动作子系统的核心代码位于：

- [`src/phoneagent/actions/protocol.py`](../../src/phoneagent/actions/protocol.py)：动作协议、解析与校验；
- [`src/phoneagent/actions/compatibility.py`](../../src/phoneagent/actions/compatibility.py)：少量供应商坐标语法兼容；
- [`src/phoneagent/actions/policy.py`](../../src/phoneagent/actions/policy.py)：无副作用的确认、任务风险与时长策略；
- [`src/phoneagent/actions/handler.py`](../../src/phoneagent/actions/handler.py)：动作执行、回调调用和结构化结果；
- [`src/phoneagent/actions/__init__.py`](../../src/phoneagent/actions/__init__.py)：动作子系统的公共导出。

动作子系统不是一个完整的 Agent 循环。模型请求、屏幕观测、动作新鲜度检查、执行后验证、恢复和轨迹记录由 [`src/phoneagent/agent.py`](../../src/phoneagent/agent.py) 与 `runtime` 子系统负责。理解这一职责边界非常重要。

## 1. 子系统要解决什么问题

视觉语言模型返回的是不可信文本，而 Android 设备操作具有真实副作用。PhoneAgent 不能把模型文本直接当成 Python 代码或 ADB 命令执行，因此动作子系统在二者之间建立了一条受控边界：

```text
模型动作文本
    ↓
供应商语法的窄兼容
    ↓
严格解析：只允许一个 do(...) 或 finish(...)
    ↓
封闭 Schema 校验与值归一化
    ↓
任务边界、风险审核与人工确认
    ↓
坐标新鲜度检查（runtime 负责）
    ↓
ActionHandler 再次校验并派发
    ↓
AndroidDevice / 回调函数
    ↓
ActionResult
    ↓
执行后验证与恢复（runtime 负责）
```

它主要承担以下职责：

1. 将模型动作限制在一个封闭、可审计的动作集合中；
2. 拒绝动态表达式、未知字段、多动作输出和越界参数；
3. 将不同模型供应商的少数坐标标记归一化为统一格式；
4. 在设备执行前识别敏感操作和显式任务边界；
5. 将归一化坐标转换为当前设备的真实像素坐标；
6. 为设备异常、用户取消和回调缺失生成结构化结果；
7. 保持协议、策略和执行三层之间的职责分离。

它不负责证明任务已经完成，也不负责证明一次点击产生了预期语义效果。这两类判断属于任务完成复核和执行后验证。

## 2. 四层结构

### 2.1 Compatibility：窄兼容层

`compatibility.py` 只处理部分视觉模型常见的点坐标标记，例如：

```text
element=[<point>250 126</point>]
element=<point_2d>(250, 126)</point_2d>
element=<|point_start|>(250,126)<|point_end|>
```

它们会被转换为：

```text
element=[250, 126]
```

兼容层遵守“只转换，不推断”的原则：

- 只识别 `element`、`start`、`end` 后面的两个数值坐标；
- 不推断动作类型；
- 不接受 box、bbox、多点列表或动态表达式；
- 不改写普通字符串内部的类似文本；
- 未被明确允许的标记会保留原样，随后由严格解析器拒绝。

因此，兼容层不是宽松的模型输出修复器。它只消除已知供应商格式与 PhoneAgent 标准协议之间的一小段语法差异。

### 2.2 Protocol：协议与校验层

`protocol.py` 定义了 PhoneAgent 可以接受的动作语言。模型每轮只能返回一个完整调用：

```python
do(action="Tap", element=[500, 300])
```

或者：

```python
finish(message="任务完成", success=True)
```

解析入口是 `parse_action(response)`，其处理顺序为：

1. 去除首尾空白，并拒绝空输出和 Markdown 代码块；
2. 调用 `normalize_provider_action_syntax()` 处理允许的坐标标记；
3. `_extract_single_call()` 扫描括号与引号，提取且只允许一个完整调用；
4. 使用 `ast.parse(..., mode="eval")` 解析调用结构；
5. 使用 `ast.literal_eval()` 读取每个关键字的字面量值；
6. 调用 `validate_action()` 执行封闭 Schema 校验和归一化。

这里没有使用 `eval()`。下面的模型输出会被拒绝，而不会执行：

```python
do(action="Tap", element=__import__("os").system("id"))
```

协议还会拒绝：

- JSON 动作；
- Markdown 代码块；
- 位置参数；
- `**kwargs` 展开；
- 重复关键字；
- 未知关键字；
- 缺失必填字段；
- 一个响应中的多个动作；
- 动作调用后的额外文字；
- 不完整的括号或字符串；
- 不支持的动作名称。

`parse_action()` 只应接收已经由模型响应层分离出的动作正文。模型的 reasoning 或前缀说明由 `ModelResponseParser` 处理，不属于本模块的输入协议。

### 2.3 Policy：无副作用策略层

`policy.py` 不操作设备，只根据动作和用户原始任务返回判断结果。它包含三组策略：

- 动作自身的敏感操作确认；
- 基于用户任务的风险分类和禁止边界检查；
- `Wait` 时长解析。

策略函数保持无副作用，因此可以独立测试，也可以在设备执行前被主循环调用。

### 2.4 Handler：执行层

`handler.py` 中的 `ActionHandler` 是动作子系统的设备派发边界。它接收已经解析的字典动作，但仍会调用 `validate_action()` 再校验一次，以保护直接注入的程序化动作。

它负责：

- 调用 `AndroidDevice` 的允许方法；
- 调用人工确认、接管、记录和 API 回调；
- 进行归一化坐标到像素坐标的转换；
- 限制等待时长和手势持续时间；
- 捕获设备异常并转换成 `ActionResult`；
- 在任务结束时恢复输入法。

## 3. 动作的数据表示

当前实现使用普通 `dict[str, Any]` 表示动作，而不是为每种动作定义一个类。动作通过 `_metadata` 区分执行动作和终止动作。

### 3.1 `do` 动作

```python
{
    "_metadata": "do",
    "action": "Tap",
    "element": [500, 300],
    "description": "点击搜索按钮",
}
```

`do(**kwargs)` 只是一个方便程序调用的构造函数：

```python
do(action="Back")
```

它本身不会做校验。调用者仍需经过 `validate_action()`，或者交给 `ActionHandler.execute()` 进行防御性校验。

### 3.2 `finish` 动作

```python
{
    "_metadata": "finish",
    "message": "任务完成",
    "success": True,
}
```

`finish()` 的默认值是：

```python
finish(message="Task completed", success=True)
```

`finish(success=True)` 在主循环中只是 Planner 提出的“任务已完成”声明。当前代码会先获取新截图并进行隔离的任务完成复核，复核通过后才会把它交给 `ActionHandler` 形成终止结果。

`finish(success=False)` 不需要成功复核，会直接作为失败终止动作处理。

和 `do()` 一样，`finish()` 构造函数可以临时产生带额外字段的字典，但 `validate_action()` 只允许 `_metadata`、`message` 和 `success`，额外字段最终会被拒绝。

### 3.3 `ActionResult`

所有执行路径最终返回：

```python
@dataclass(slots=True)
class ActionResult:
    success: bool
    should_finish: bool
    message: str | None = None
    requires_confirmation: bool = False
    error_code: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

各字段含义如下：

| 字段 | 含义 |
| --- | --- |
| `success` | 本次动作处理或设备命令是否成功，不代表整个用户任务语义正确 |
| `should_finish` | 这次结果是否要求结束当前任务 |
| `message` | 给主循环、用户或轨迹使用的可读信息 |
| `requires_confirmation` | 结果是否来自敏感操作确认流程 |
| `error_code` | 可供恢复策略判断的稳定错误类别 |
| `metadata` | 坐标、持续时间、包名、系统面板结果等结构化证据 |

必须区分三个层次：

```text
ActionResult.success
    ≠ 执行后的界面效果已经被验证
    ≠ 整个用户任务已经完成
```

例如，ADB 成功发送一次 Tap 只能证明命令派发没有报错，不能证明点中了正确按钮，也不能证明整个任务完成。

## 4. 支持的动作协议

所有 `do` 动作都可以使用以下公共策略字段：

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `description` | `str` | 描述动作意图，也会参与敏感关键词判断 |
| `message` | `str` | 提示信息；部分动作将其作为必填内容 |
| `sensitive` | `bool` | 模型显式声明敏感操作 |
| `requires_confirmation` | `bool` | 模型显式要求人工确认 |
| `risk_level` | `low / medium / high` | 风险等级；`high` 强制确认 |

每种动作的专用字段和执行行为如下：

| 标准动作名 | 必填字段 | 可选专用字段 | 执行行为 |
| --- | --- | --- | --- |
| `Launch` | `app` | 无 | 解析应用别名或包名并启动应用 |
| `Tap` | `element` | 无 | 单击归一化坐标 |
| `Type` | `text` | `clear` | 必要时准备 ADB 输入法，清空并输入文本 |
| `Swipe` | `start`, `end` | `duration_ms` | 在两个归一化坐标之间滑动 |
| `Back` | 无 | 无 | 发送返回操作 |
| `Home` | 无 | 无 | 回到桌面 |
| `OpenNotifications` | 无 | 无 | 请求展开通知面板 |
| `OpenQuickSettings` | 无 | 无 | 请求展开快捷设置面板 |
| `CloseSystemPanel` | 无 | 无 | 请求收起系统面板 |
| `Double Tap` | `element` | 无 | 双击归一化坐标 |
| `Long Press` | `element` | `duration_ms` | 长按归一化坐标，默认 800 ms |
| `Wait` | 无 | `duration` | 等待一段有上限且可取消的时间 |
| `Take_over` | `message` | 无 | 请求用户接管操作，完成后继续 |
| `Interact` | `message` | 无 | 请求用户作选择或交互，完成后继续 |
| `Note` | `message` | 无 | 记录一条运行时笔记并触发可选回调 |
| `Call_API` | `instruction` | 无 | 将指令传给显式配置的 API 回调 |

协议支持有限的名称别名，并统一成上表中的标准名称。例如：

- `tap` → `Tap`；
- `type_name` / `typename` → `Type`；
- `double_tap` / `doubletap` → `Double Tap`；
- `open_quick_settings` → `OpenQuickSettings`；
- `callapi` → `Call_API`。

名称归一化只处理大小写、连续空白以及连字符到下划线的转换，不会对未知动作做模糊猜测。

## 5. Schema 校验规则

`validate_action()` 是动作字典的统一可信边界。

### 5.1 封闭字段集合

每种动作只能携带公共字段和该动作声明的专用字段。例如：

```python
do(action="Back", unexpected="value")
```

会因为 `unexpected` 不在 `Back` 的允许集合中而被拒绝。封闭字段集合可以防止模型把未设计、未审计的参数传入执行层。

### 5.2 坐标规则

`Tap`、`Double Tap`、`Long Press` 使用 `element`，`Swipe` 使用 `start` 和 `end`。坐标可以表示为：

```python
[500, 300]
```

也可以表示为键严格等于 `x`、`y` 的字典：

```python
{"x": 500, "y": 300}
```

校验后统一为两个元素的列表。每个坐标必须满足：

- 是 `int` 或 `float`，但不能是 `bool`；
- 是有限数值，不能是 `NaN` 或无穷大；
- 位于闭区间 `0..999`。

PhoneAgent 使用与设备分辨率无关的归一化坐标：左上角为 `[0, 0]`，右下角为 `[999, 999]`。

### 5.3 文本、布尔值和风险等级

- `Launch.app` 必须是非空字符串；
- `Type.text` 会转换成字符串，但不能超过 20,000 个字符；
- `Type.clear` 必须是布尔值；
- `Take_over.message`、`Interact.message`、`Note.message` 必须是非空字符串；
- `Call_API.instruction` 必须是非空字符串；
- `sensitive` 和 `requires_confirmation` 必须是布尔值；
- `risk_level` 会转成小写，只允许 `low`、`medium`、`high`；
- `Long Press` 和 `Swipe` 的 `duration_ms` 必须能转换为正整数；
- `finish.success` 必须是布尔值。

模型输出中的原始换行只会在已闭合的引号字符串内部被转义，以支持多行 `message` 或 `text`；这不会放宽动作结构本身。

## 6. 安全策略

动作安全不是只依赖模型是否主动设置了 `sensitive=True`。当前实现同时检查模型动作、用户原始任务和最新截图。

### 6.1 动作自身的确认规则

`confirmation_message()` 按以下顺序判断是否需要确认：

1. `sensitive=True` 或 `requires_confirmation=True`；
2. `risk_level="high"`；
3. 动作描述文本包含敏感关键词；
4. 当前任务属于后果性任务，动作是坐标动作，而且尚未完成任务风险审核。

敏感文本来自 `label`、`description`、`instruction`、`message`、`target`。对于正常的模型协议动作，封闭 Schema 主要允许其中的 `description`、`instruction` 和 `message`；`label`、`target` 使独立策略函数也能服务于其他程序化调用者，但它们不能通过标准动作 Schema。

敏感关键词覆盖支付、购买、发送、发布、删除、授权、预约、拨号、保存、提交等中英文表达。

应用名称不等于敏感操作授权。例如“打开支付宝”不会仅仅因为应用名中含有“支付”而被判断为支付行为。

### 6.2 用户任务风险分类

`task_risk_reasons(task)` 从用户原始任务中只识别两类高后果风险：

| 风险类别 | 示例 |
| --- | --- |
| `financial_or_commercial` | 支付、转账、提现、购买、下单、贷款、投资交易 |
| `credential_or_account_security` | 密码、验证码、PIN、密钥、助记词、银行卡绑定、账户注销 |

如果用户任务属于这些类别，并且 Planner 给出 `Tap`、`Double Tap`、`Long Press` 或 `Swipe`，`action_needs_task_risk_review()` 会要求主循环进行一次隔离的截图风险审核。显式否定边界是该函数的另一个独立触发条件，不要求任务同时属于这两类高后果风险。

普通系统设置、一般通信、普通文件删除、预约等任务若没有显式否定边界，不会仅凭任务文本触发这套模型审核；动作自身明确带有 `sensitive=True`、高风险等级或敏感描述时，原有确定性人工确认仍然有效。单纯打开支付宝或银行应用也不等于授权资金操作。

风险审核实现位于 [`src/phoneagent/runtime/semantic.py`](../../src/phoneagent/runtime/semantic.py)，输出只有三种有效结论：

- `ALLOW`：动作可以继续；
- `CONFIRM`：动作必须经过人工确认；
- `BLOCK`：动作不得派发，返回主循环重新规划。

审核输出无效、审核不确定或审核功能被关闭时，不会自动放行，而是退化到人工确认。

### 6.3 显式禁止边界

`task_has_negative_boundary()` 识别“不要发送”“禁止提交”“停留在发送前”“do not pay”等明确限制。

`task_scope_violation_message()` 的确定性阻断比较保守：只有任务存在明确禁止边界，并且动作自身的描述又明确指向敏感效果时才直接阻断。例如：

```text
任务：输入消息，停留在发送前，不要发送
动作：do(action="Tap", element=[800, 900], description="点击发送按钮")
```

该动作会返回 `task_scope_violation`，并记录 `command_dispatched=False`。如果坐标动作没有足够
清晰的描述，确定性规则不会猜测其效果，而是仅凭显式否定边界继续进入截图风险审核；因此
普通通信、删除、预约等任务中的无描述坐标动作也不能绕过用户明确写出的限制。

确定性边界检查只覆盖可直接产生外部副作用的坐标动作和 `Call_API`。`finish`、`Note`、
`Take_over` 等终止或纯消息动作被明确排除，因此
`finish(message="已输入但未发送")` 不会因为完成说明中的“发送”二字产生误阻断。

### 6.4 时长策略

`parse_duration_seconds()` 支持：

- 数字秒数；
- 包含 `ms` / `毫秒` 的毫秒文本；
- 包含 `minute` / `min` / `分钟` 的分钟文本；
- 普通秒数文本。

负数会归零，无法识别数值时默认 1 秒。最终等待时间还会被 `ActionHandler.max_wait_seconds` 限制，默认最大 15 秒。

## 7. 执行流程

### 7.1 主循环中的真实顺序

动作在 `PhoneAgent._accept_step_action_async()` 中解析，在 `PhoneAgent._execute_accepted_action_async()` 中进入执行流程。当前顺序为：

```text
1. parse_action：解析并校验
2. 写入 AgentState 和 ACTION 轨迹事件
3. 如果是 finish(success=True)，先做任务完成复核
4. 检查确定性的任务禁止边界
5. 必要时做截图支持的任务风险审核
6. 对坐标动作执行人工确认
7. 对坐标动作重新截图，执行新鲜度检查
8. 检查重复且停滞的动作
9. ActionHandler.execute：再次校验并派发
10. 记录 EXECUTION 事件
11. 非终止动作进入执行后验证
12. 根据验证结果继续、恢复或结束
```

步骤 6 位于步骤 7 之前：用户确认期间界面可能变化，因此确认完成后必须重新观测，不能直接使用确认前的截图坐标。

非坐标动作不会经过坐标新鲜度检查，`ActionHandler.execute()` 会在内部完成尚未执行的普通确认检查。

### 7.2 坐标换算

模型坐标通过以下关系映射到实际像素：

```text
pixel = round(relative / 999 × (size - 1))
```

最终像素还会被限制在 `0..size-1`。因此在 `1080 × 2400` 屏幕上：

```text
[0, 0]       → (0, 0)
[999, 999]   → (1079, 2399)
[500, 500]   → (540, 1201)
```

使用 `size - 1` 可以确保归一化右下角不会转换成屏幕范围外的像素。

### 7.3 设备派发

`ActionHandler.execute()` 首先防御性校验动作。如果是 `finish`，它不调用设备，直接构造终止结果。对于 `do` 动作，它从一个封闭的 handler 映射中选择对应方法。

设备方法抛出的异常会统一转换为：

```python
ActionResult(
    success=False,
    should_finish=False,
    message="<ActionName> failed: ...",
    error_code="action_execution_failed",
    metadata={"exception_type": "..."},
)
```

这样设备异常不会穿透执行边界直接破坏 Agent 循环，恢复子系统也能基于稳定的错误码决策。

## 8. 各类动作的执行细节

### 8.1 Launch

如果设备实现 `launch_app_resolved()`，Handler 使用该方法获得结构化 `AppLaunchResult`，并在 metadata 中保留：

- 用户提供的应用名；
- 解析后的包名和显示名；
- 完整的应用启动结果。

为兼容简单的第三方设备适配器，缺少该方法时会退回 `launch_app()`。未知别名返回 `app_not_found`，已配置但未安装等情况可由设备层返回更具体的错误码。

### 8.2 Tap、Double Tap、Long Press、Swipe

这些动作先把 `0..999` 坐标转换为真实像素，再调用设备方法。实际像素和手势持续时间会写入 `ActionResult.metadata`。

`Long Press` 默认持续 800 ms；`Long Press` 和 `Swipe` 的持续时间都会被 `max_gesture_duration_ms` 限制，默认最大 10,000 ms。

这四类动作是截图绑定动作。主循环会在真正派发前重新截图并验证目标区域是否仍与规划截图兼容。该保护由 runtime freshness guard 实现，不在 Handler 内部。

### 8.3 Type 与输入法生命周期

第一次执行 `Type` 时，如果设备支持 `detect_and_set_adb_keyboard()`，Handler 会保存原始输入法并切换到适合 ADB 输入的键盘。后续 `Type` 不会重复准备键盘。

如果 `clear=True`，执行顺序为：

```text
clear_text()
type_text(text)
```

任务结束时，`PhoneAgent._finalize_run()` 调用 `restore_input_method()` 恢复首次保存的输入法。恢复失败不会覆盖任务结果，而是记录 `keyboard_restore_failed` 错误事件。

### 8.4 Wait 与取消

如果配置了共享的 `cancel_event`，`Wait` 使用 `Event.wait(duration)`，因此用户取消任务时可以立即醒来，而不必等待完整时长。

被取消的 Wait 返回：

```text
success=False
should_finish=True
error_code=user_cancelled
```

如果请求时长超过上限，动作仍可成功，但 `message` 和 metadata 会记录原始时长与实际等待时长。

### 8.5 Take_over 与 Interact

两者都调用 `takeover_callback(message)`：

- `Take_over` 表达“需要人工接管”；
- `Interact` 表达“需要用户选择或交互”。

默认回调通过终端 `input()` 阻塞，用户完成手工操作并按 Enter 后，Agent 继续下一轮观测和规划。Web 运行时可以注入自己的回调实现。

### 8.6 Note

`Note` 将消息追加到 `ActionHandler.notes`，并调用可选的 `note_callback`。它不直接操作 Android 设备。

正常协议已经要求非空 `message`。Handler 内仍保留 `empty_note` 防御分支，以避免未来内部调用绕过协议时静默记录空内容。

### 8.7 Call_API

`Call_API` 只调用显式注入的 `api_callback(instruction)`。如果运行时没有配置该回调，返回 `api_callback_not_configured`，不会自行寻找或调用外部 API。

`instruction` 会参与敏感关键词判断，因此包含发送、支付、删除等效果的 API 指令仍可能触发确认。

### 8.8 系统面板动作

`OpenNotifications`、`OpenQuickSettings` 和 `CloseSystemPanel` 是语义动作，而不是让模型猜测屏幕边缘坐标。

打开面板时，设备层首先使用受控的系统命令。主循环随后验证 WindowManager 中的面板状态。如果打开命令失败或面板未出现，主循环只对两个“打开”动作调用一次 `execute_system_panel_fallback()`，使用受控边缘手势重试。

该 fallback 不会暴露成新的模型动作，但主命令、fallback、最终 transport 和验证结果都会进入 metadata。关闭面板不会使用盲目的 Back 作为 fallback。

## 9. 确认流程

`ActionHandler.request_confirmation()` 可以在不派发动作的情况下单独执行确认。它的返回约定是：

- 返回 `None`：不需要确认，或者用户已经确认；
- 返回 `ActionResult`：动作无效，或者用户拒绝。

用户拒绝时结果为：

```text
success=False
should_finish=True
requires_confirmation=True
error_code=user_cancelled
message=User cancelled sensitive operation
```

坐标动作由主循环先调用 `request_confirmation()`，再做新鲜度检查，最后以 `confirmation_checked=True` 调用 `execute()`，避免重复询问。

`task_risk_checked=True` 表示主循环已经处理过任务级风险结论。它只防止重复触发同一个保守任务确认，不会绕过 `sensitive=True`、`requires_confirmation=True`、`risk_level=high` 或动作敏感文本产生的确认。

## 10. 错误与恢复边界

动作子系统产生或传递的常见错误包括：

| 错误码 | 来源 | 含义 |
| --- | --- | --- |
| `invalid_action` | Handler | 程序化注入的动作未通过 Schema 校验 |
| `user_cancelled` | 确认或 Wait | 用户拒绝敏感操作或取消等待 |
| `action_execution_failed` | Handler | 设备方法抛出异常 |
| `app_not_found` | Launch | 应用别名或包名无法解析 |
| `app_not_installed` | 设备启动层 | 已解析应用未安装在目标设备 |
| `system_panel_command_failed` | 系统面板动作 | 系统面板语义命令失败 |
| `system_panel_fallback_failed` | 面板 fallback | 受控边缘手势执行失败 |
| `api_callback_not_configured` | Call_API | 运行时没有提供 API 回调 |

与动作紧密相关、但由主循环或 runtime 产生的错误包括：

| 错误码 | 含义 |
| --- | --- |
| `action_parse_error` | 模型动作文本不能被严格协议解析 |
| `model_output_truncated` | 模型输出在形成完整动作前被截断 |
| `task_scope_violation` | 动作违反任务边界或被风险审核阻断 |
| `pre_action_observation_changed` | 坐标动作派发前界面已变化，命令未发送 |
| `pre_action_observation_failed` | 派发前无法获得可信的新观测 |
| `repeated_action_blocked` | 同一坐标动作在停滞界面上重复出现 |

`ActionHandler` 不决定一个失败是否应该重试。它只返回事实；是否重规划、重新观测、重试安全动作、请求接管或终止，由 recovery 子系统决定。

## 11. 一个完整例子

高后果任务示例：

```text
从银行卡转账 100 元给张三
```

Planner 在确认转账页面输出：

```python
do(
    action="Tap",
    element=[870, 910],
    description="点击确认转账按钮",
)
```

运行过程为：

1. `parse_action()` 将文本解析成标准动作字典；
2. `task_risk_reasons()` 将任务识别为 `financial_or_commercial`；
3. 因为 Tap 是坐标动作，主循环发起截图风险审核；
4. 审核应返回 `CONFIRM`，主循环要求用户确认；
5. 用户确认后，系统重新截图并检查确认转账按钮区域是否仍然一致；
6. Handler 把 `[870, 910]` 转换成当前屏幕像素；
7. `AndroidDevice.tap(x, y)` 派发设备命令；
8. Handler 返回命令级 `ActionResult`；
9. runtime 再观察屏幕并验证动作效果；
10. Planner 后续提出 `finish(success=True)` 时，还要经过独立的任务完成复核。

如果任务改为：

```text
输入消息“晚上见”，停留在发送前，不要发送
```

同一个带有“点击发送按钮”描述的动作会在步骤 3 之前被确定性边界检查阻断，设备不会收到 Tap 命令。

## 12. 为什么这样设计

### 12.1 严格拒绝优于猜测修复

模型输出错误时，运行时进入有界协议恢复，而不是猜测模型本来想执行什么。对真实设备而言，一次错误修复可能直接造成不可逆副作用。

### 12.2 协议、策略和执行分离

- Protocol 回答“这个动作是否合法”；
- Policy 回答“这个动作是否应该确认或阻断”；
- Handler 回答“如何执行并返回什么结果”；
- Runtime 回答“界面是否仍适合执行、执行效果是否成立、失败后怎么办”。

分离后，各层可以独立测试，安全规则也不会隐藏在具体 ADB 方法中。

### 12.3 Handler 仍然重复校验

模型路径已经调用过 `parse_action()`，但库使用者也可能直接调用：

```python
handler.execute(do(action="Tap", element=[500, 300]), width, height)
```

所以执行边界必须再次校验，不能依赖所有上游都正确使用协议层。

### 12.4 归一化坐标与新鲜度检查配合

归一化坐标解决不同设备分辨率的问题，但不能解决 UI 在模型推理期间发生变化的问题。因此坐标协议和 pre-action freshness guard 必须同时存在。

## 13. 当前限制

1. 动作使用字典表示，类型错误主要在运行时发现，而不是由静态类型系统发现；
2. 关键词和正则策略不可能覆盖所有语言表达，仍需截图风险审核和人工确认兜底；
3. 任务风险审核是模型判断，可能与 Planner 使用同一个模型，不能视为外部事实；
4. 坐标动作仍依赖视觉定位，新鲜度检查只能降低误点风险，不能数学上消除截图与派发之间的竞态；
5. `ActionResult.success` 主要是命令级事实，必须结合执行后验证使用；
6. `Call_API` 的能力和副作用取决于调用方注入的回调，部署者必须控制该信任边界；
7. 敏感关键词与任务正则目前以中英文常见表达为主，跨语言覆盖有限。

## 14. 建议阅读顺序

如果要从代码中完整理解动作子系统，建议按以下顺序阅读：

1. `protocol.py` 中的 `_ACTION_ALIASES`、字段 Schema 和 `validate_action()`；
2. `parse_action()` → `_extract_single_call()` → `_parse_do_call()` / `_parse_finish_call()`；
3. `compatibility.py` 中的 `normalize_provider_action_syntax()`；
4. `policy.py` 中的 `task_risk_reasons()`、`task_scope_violation_message()`、`confirmation_message()`；
5. `handler.py` 中的 `ActionResult`、`request_confirmation()`、`execute()`；
6. Handler 内每个 `_handle_*` 方法；
7. `agent.py` 中的 `_accept_step_action_async()` 和 `_execute_accepted_action_async()`；
8. 最后阅读 freshness、verification、recovery 和 semantic review，理解动作子系统的上下游。

## 15. 对应测试

协议和安全边界主要由以下测试固定：

- [`tests/test_action_protocol.py`](../../tests/test_action_protocol.py)：严格协议、AST 字面量解析、字段 Schema、坐标兼容和模型响应边界；
- [`tests/test_actions.py`](../../tests/test_actions.py)：坐标换算、等待取消、输入法恢复、确认策略、任务风险和系统面板动作；
- [`tests/test_agent_loop.py`](../../tests/test_agent_loop.py)：动作进入完整主循环后的风险审核、边界阻断、新鲜度检查、验证和恢复行为。

可以分别运行：

```bash
uv run pytest tests/test_action_protocol.py -q
uv run pytest tests/test_actions.py -q
uv run pytest tests/test_agent_loop.py -q
```

阅读测试时，可以反复追问三个问题：

1. 什么输入能够进入下一层？
2. 失败时是否已经产生设备副作用？
3. 返回的成功究竟是解析成功、命令成功、效果验证成功，还是任务成功？

只要能够清楚回答这三个问题，就已经抓住了 PhoneAgent 动作子系统的核心设计。
