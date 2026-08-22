# PhoneAgent Android Device & Observation Subsystem（设备与观测子系统）

本文依据当前 [`src/phoneagent/devices`](../../src/phoneagent/devices) 与 [`src/phoneagent/adb`](../../src/phoneagent/adb) 实现，说明 PhoneAgent 如何连接 Android 设备、获得可信屏幕观测，并把高层动作转换为受控 ADB 操作。

## 1. 职责与边界

这个子系统位于 Agent 与真实手机之间：

```text
PhoneAgent / ActionHandler
        ↓
AndroidDevice：高层设备适配器
        ↓
adb.command / connection / device / screenshot
        ↓
adb 可执行程序
        ↓
真实 Android 设备
```

它负责设备连接、截图、窗口状态、应用启动、输入和系统操作，但不负责：

- 决定下一步执行什么动作；
- 判断动作是否越过用户任务边界；
- 判断旧截图上的坐标现在是否仍然有效；
- 判断执行后的界面变化是否完成用户任务。

这些职责分别属于 Model、Action Policy、Freshness、Verification 和 Semantic Review。

## 2. 源码结构

| 文件 | 职责 |
| --- | --- |
| [`devices/android.py`](../../src/phoneagent/devices/android.py) | Agent 使用的高层 Android 设备接口和结构化结果 |
| [`adb/command.py`](../../src/phoneagent/adb/command.py) | 构造并执行受检查的 ADB 命令 |
| [`adb/connection.py`](../../src/phoneagent/adb/connection.py) | USB、模拟器、局域网和远程 ADB 连接管理 |
| [`adb/device.py`](../../src/phoneagent/adb/device.py) | 点击、滑动、窗口状态、应用、输入法等设备原语 |
| [`adb/screenshot.py`](../../src/phoneagent/adb/screenshot.py) | 截图采集、校验、编码和显式诊断 fallback |
| [`adb/input.py`](../../src/phoneagent/adb/input.py) | 旧输入模块的兼容导出，实际实现位于 `adb/device.py` |

`AndroidDevice` 是正常运行时应依赖的接口；`adb/*` 是更低层的实现细节和诊断能力。

## 3. 核心数据模型

### 3.1 `Screenshot`

`Screenshot` 同时记录模型图像与真实设备坐标空间：

| 字段 | 含义 |
| --- | --- |
| `base64_data` | 发送给模型和图像比较模块的 Base64 数据 |
| `width` / `height` | 编码后图像尺寸，可能经过缩放 |
| `display_width` / `display_height` | Android 原始显示尺寸，用于动作坐标换算 |
| `mime_type` | `image/png`、`image/jpeg` 或 `image/webp` |
| `timestamp` | 截图采集时间 |
| `available` | 是否来自真实、可用的设备截图 |
| `is_blank` | 是否接近全黑保护屏 |
| `is_sensitive` | fallback 或受保护画面的敏感标记 |
| `sha256` | 编码图像内容摘要 |
| `error` | 不可用截图的原因 |

不能混淆编码尺寸和显示尺寸。模型可以看到缩小后的图像，但 ActionHandler 必须根据显示尺寸计算真实像素。

### 3.2 `ScreenObservation`

`AndroidDevice.observe()` 返回：

```text
ScreenObservation
├── screenshot
├── current_app
├── current_package
├── system_panel_visible
└── system_panel_name
```

`to_screen_info()` 将这些信息转换成紧凑 JSON 元数据，并明确声明坐标系为 `relative_0_999`。模型上下文、Freshness、Verification 和轨迹记录都复用这一个观测对象。

### 3.3 结构化设备结果

- `AppLaunchResult`：应用别名解析、安装检查和启动结果；
- `SystemPanelCommandResult`：`cmd statusbar` 请求的目标、命令、返回码及截断输出；
- `InstalledConfiguredApp`：内置应用表与设备已安装包的交集。

这些结果保留稳定错误码和证据，避免上层根据异常文字猜测状态。

## 4. 可信观测流程

`AndroidDevice.observe()` 的顺序是：

```text
ensure_ready()
→ get_screenshot(...)
→ get_window_state()
→ 解析 current_package
→ 构造 ScreenObservation
```

### 4.1 设备就绪检查

`ensure_ready()` 调用：

```text
adb [-s DEVICE_ID] get-state
```

只有返回码为 0 且输出严格为 `device` 才算可用，否则抛出 `DeviceUnavailableError`。查询命令允许一次传输级重试。

### 4.2 截图采集

真实截图使用：

```text
adb exec-out screencap -p
```

采集后依次检查：

1. ADB 返回码；
2. stdout 是否为空；
3. 数据是否以 PNG 文件头开始；
4. stderr 是否包含失败、权限或 secure flag 标记；
5. Pillow 是否能解码；
6. 图像尺寸是否合法；
7. 图像是否接近均匀全黑。

成功后保留原始显示尺寸，再按 `max_size` 等比例缩小模型图像，最后按 PNG、JPEG 或 WebP 编码。

全黑判断使用最大 `64 × 64` 的灰度样本：均值小于 2 且方差小于 1 才视为近乎均匀黑屏，普通深色 UI 不应被轻易拒绝。

### 4.3 截图失败策略

默认 `allow_fallback=False`，失败会抛出明确异常：

- `ScreenshotPermissionError`：secure flag 或权限阻止；
- `ScreenshotDecodeError`：数据不是可信图像；
- `ScreenshotTimeoutError`：ADB 截图超时；
- `ScreenshotCaptureError`：其他采集失败。

只有诊断模式显式允许 fallback 时，才创建黑色占位图，并标记：

```text
available=False
is_blank=True
error=<真实失败原因>
```

因此 fallback 不会伪装成成功观测。Agent 主循环仍会拒绝不可用或空白截图。

### 4.4 前台应用与系统面板

`get_window_state()` 读取 `dumpsys window`，从不同 Android 版本的焦点字段中提取包名：

- `mCurrentFocus`；
- `mFocusedApp`；
- `topResumedActivity`；
- `mTopActivity`。

包名会映射为内置标准应用名；常见 Launcher 返回 `System Home`；未知包返回 `Unknown (<package>)`；完全无法解析时返回 `Unknown`。

通知面板不能仅凭 WindowManager 中存在 `NotificationShade` 判断。代码优先检查它是否获得焦点，否则检查对应 Window block 的 `isVisible=true` 或 `surface: shown=true`。已注册但隐藏的面板返回 `False`，无法识别的 OEM 状态返回 `None`。

## 5. ADB 命令边界

`build_adb_command()` 只按参数列表构造命令：

```text
adb [-s DEVICE_ID] <args...>
```

没有通过 shell 拼接命令字符串。`run_adb()` 使用 `subprocess.run()`，支持：

- stdout/stderr 捕获；
- 文本或二进制模式；
- 超时；
- 是否检查非零返回码；
- 有界重试和线性退避。

重试只针对 `device offline`、transport error、connection reset 等传输错误。语义失败不会自动重试，尤其不能重复有副作用的 input 命令。

失败统一包装为 `ADBCommandError`，保留命令、返回码、截断 stdout/stderr、失败原因和尝试次数。

## 6. 设备动作原语

[`adb/device.py`](../../src/phoneagent/adb/device.py) 提供 ActionHandler 最终调用的设备原语：

| 原语 | ADB 实现 |
| --- | --- |
| `tap` | `shell input tap x y` |
| `double_tap` | 两次 tap，中间使用配置间隔 |
| `long_press` | 同一点起止的 `input swipe` |
| `swipe` | `shell input swipe`，未指定时长时按距离估算 250–1000 ms |
| `back` | `KEYCODE_BACK` |
| `home` | `KEYCODE_HOME` |
| `statusbar_command` | 仅允许 expand-notifications、expand-settings、collapse |

坐标必须是非负整数，手势持续时间必须是正整数。每个操作完成后按 TimingConfig 设置短暂等待，使 Android 有时间更新界面。

## 7. 应用启动

应用启动是惰性、确定性的，不会在每个任务开始时枚举全部安装应用：

```text
Launch(app)
→ get_package_name(app)
→ pm path 检查安装状态
→ monkey -p PACKAGE -c android.intent.category.LAUNCHER 1
→ 返回 AppLaunchResult
→ Verification 检查前台包
```

未知人类名称返回 `app_not_found`，已配置但未安装返回 `app_not_installed`，ADB 启动失败返回 `app_launch_failed`。

`list_launchable_apps()` 是显式诊断操作，会查询所有安装包并返回“内置配置包 ∩ 已安装包”；它不被 Agent 主循环调用，也不建立持久应用目录。

## 8. 文本输入和输入法

PhoneAgent 使用 ADB Keyboard 的 Base64 广播，而不是 `adb shell input text`：

```text
UTF-8 文本
→ Base64
→ am broadcast -a ADB_INPUT_B64 --es msg <encoded>
```

这避免中文、空格、引号等 shell 转义问题。第一次 Type 前，Handler 保存当前 IME，并在需要时切换到 `com.android.adbkeyboard/.AdbIME`；任务结束时恢复原输入法。

清空输入框使用 `ADB_CLEAR_TEXT` 广播。ADB Keyboard 未安装或无法启用时，Type 明确失败，不会退化到不可靠的字符输入方式。

## 9. 系统面板

打开通知或快捷设置首先使用 allowlist 中的 `cmd statusbar` 命令。命令返回 0 仍不等于面板已经显示，所以 Verification 还会检查 WindowManager。

当打开命令失败或面板未出现时，Agent 编排层可以调用 `open_system_panel_gesture()`：

- 通知面板：屏幕顶部左侧向下滑；
- 快捷设置：屏幕顶部右侧向下滑；
- 起点约为高度 3%，终点约为 82%，持续 650 ms。

这是运行时内部 fallback，不是模型可自由构造的新动作。关闭面板没有 Back fallback。

## 10. 连接管理

`ADBConnection` 支持：

- USB 设备；
- `emulator-*` 模拟器；
- 私有 IP 的 Wi-Fi ADB；
- 公网 IP 或域名形式的远程 ADB。

它可以连接、断开、列出设备、启用 TCP/IP、查询设备 IP、Android 版本和重启 ADB Server。未指定 device_id 时，运行时只会自动选择唯一一个处于 `device` 状态的设备；没有可用设备或存在多个可用设备都要求调用者明确处理。

连接管理的 `_run()` 保留较宽松的 CompletedProcess 接口，便于分析 `adb connect` 的 stdout/stderr；正常设备命令则优先使用会产生 `ADBCommandError` 的共享 `run_adb()`。

## 11. 与其他子系统的连接

```text
Entry/CLI ──设备预检──> ADBConnection + Screenshot
Agent ──observe──> AndroidDevice ──> ScreenObservation
Model Context <──截图与 Screen Info── ScreenObservation
ActionHandler ──动作调用──> AndroidDevice
Freshness <──前后观测──> ScreenObservation
Verification <──执行前后观测──> ScreenObservation
Recovery ──REOBSERVE / RETRY_ACTION──> AndroidDevice
```

## 12. 当前限制

1. 前台窗口与系统面板解析依赖不同 Android/OEM 的 `dumpsys window` 文本格式，未知布局只能返回 `None`；
2. 应用别名来自静态表，未知人类应用名不会自动发现；
3. 截图和 ADB 命令不是一个原子事务，竞态由 Freshness 降低但不能消除；
4. ADB Keyboard 是可靠多语言输入的外部依赖；
5. 诊断 fallback 截图不能用于实际视觉决策；
6. Web 或远程暴露 ADB 会扩大安全边界，本模块没有替代 ADB 自身的认证机制。

## 13. 推荐阅读顺序与测试

阅读顺序：

1. `Screenshot` 与 `ScreenObservation`；
2. `AndroidDevice.observe()`；
3. `get_screenshot()` 与 `_capture_screenshot_impl()`；
4. `run_adb()`；
5. `get_window_state()`；
6. AndroidDevice 的动作方法；
7. 应用启动、输入法和系统面板；
8. 最后阅读 `ADBConnection`。

对应测试：

```bash
uv run pytest tests/test_screenshot.py -q
uv run pytest tests/test_apps.py tests/test_app_resolution.py -q
uv run pytest tests/test_actions.py -q
```
