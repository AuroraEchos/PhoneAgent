# PhoneAgent

[English](README_EN.md) | 简体中文

[项目主页](https://auroraechos.github.io/PhoneAgent/) · [GitHub](https://github.com/AuroraEchos/PhoneAgent) · [Release](https://github.com/AuroraEchos/PhoneAgent/releases/tag/v0.1.0)

PhoneAgent 是一个面向 Android 真机的轻量级视觉语言智能体运行时。它通过 ADB 获取屏幕、调用兼容 OpenAI Chat Completions API 的视觉语言模型，并执行结构化手机操作。

项目刻意保持核心循环简单：

```text
Observe -> Plan -> Execute -> Verify -> Recover/Replan -> Repeat
```

首个公开版本 `v0.1.0` 重点不是堆叠框架，而是建立一条可审计、可测试、失败有边界的手机 GUI Agent 执行链路。

## 核心能力

- **纯视觉决策**：模型根据当前截图与任务上下文选择下一步动作。
- **安全动作协议**：模型输出通过 AST/JSON 解析和参数白名单校验，不执行模型生成的 Python 代码。
- **Android 确定性能力**：动态发现可启动应用，支持高置信度 package/activity 直达。
- **动作后验证**：区分命令是否执行、是否观察到变化、是否确定性验证语义结果。
- **有界恢复**：失败后重新观察、重新规划或重试少量幂等动作；不会盲目重放 `Tap`、`Type`、`Back` 等可能产生副作用的动作。
- **完整轨迹**：记录观察、模型请求、动作、执行、验证、恢复、状态迁移和最终结果。
- **人工接管**：登录、验证码、密码、支付等敏感或不可观察页面可交由用户处理。

## 当前能力边界

PhoneAgent 当前是一个 **ADB 驱动的研究与工程原型**，不是已经部署在 Android 手机上的消费级产品。

需要明确：

- 对 `Tap`、`Swipe`、`Type` 等坐标动作，当前验证只能证明发生了可观察变化，不能证明模型点击了语义上正确的目标。
- 完整任务是否完成由规划模型通过 `finish(...)` 自我报告，尚未使用独立任务评审模型。
- 受 DRM、FLAG_SECURE 或系统保护的页面可能无法截图，运行时不会在不可观察画面上猜测坐标。
- 不同厂商 Launcher 对 `KEYCODE_SEARCH` 的支持不一致；fallback 必须观察到真实界面变化才会被接受。
- 真正端侧部署仍需要 Android 应用、`AccessibilityService`、`MediaProjection`、前台服务和完整隐私控制。

## 系统结构

```text
User Task
   |
   v
Task Runtime / State Machine
   |
   +--> Installed App Discovery / Resolver
   |       |
   |       +--> deterministic package launch
   |
   +--> Screen Observation
           |
           v
       VLM Planner
           |
           v
      Safe Action Parser
           |
           v
       ADB Executor
           |
           v
    Post-action Verifier
           |
           +--> continue
           +--> bounded recovery
           +--> manual takeover
           +--> terminal failure
```

更多实现细节见 [架构说明](docs/ARCHITECTURE.md)，首个版本变更见 [v0.1.0 Release Notes](RELEASE_NOTES_v0.1.0.md)。

项目静态主页位于 [`docs/index.html`](docs/index.html)，GitHub Pages 配置见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。

首次公开发布步骤见 [`docs/GITHUB_PUBLISH_GUIDE.md`](docs/GITHUB_PUBLISH_GUIDE.md)。

## 运行环境

- Linux（当前主要在 Ubuntu 上开发和验证）
- Python 3.12+
- Android Platform Tools / `adb`
- 已开启 USB 调试的 Android 设备
- 一个支持图像输入、兼容 OpenAI Chat Completions API 的视觉语言模型服务
- 推荐安装 [ADB Keyboard](https://github.com/senzhk/ADBKeyBoard)，用于稳定输入中文和特殊字符

## 安装

推荐使用 `uv`：

```bash
git clone https://github.com/AuroraEchos/PhoneAgent.git
cd PhoneAgent
uv sync --extra dev
```

复制环境变量模板：

```bash
cp .env.example .env
```

配置模型服务：

```dotenv
PHONE_AGENT_BASE_URL=http://localhost:8000/v1
PHONE_AGENT_MODEL=your-vision-language-model
PHONE_AGENT_API_KEY=EMPTY
PHONE_AGENT_DEVICE_ID=
```

检查 CLI：

```bash
uv run phoneagent --version
uv run phoneagent --help
```

## 设备准备

确认 ADB 可以发现设备：

```bash
adb devices
```

常用连接命令：

```bash
uv run phoneagent --list-devices
uv run phoneagent --connect 192.168.1.100:5555
uv run phoneagent --enable-tcpip 5555
```

列出设备上动态发现的可启动应用：

```bash
uv run phoneagent --list-apps
```

## 基本使用

```bash
uv run phoneagent "打开设置"
```

多步骤任务会进入视觉 Agent Loop：

```bash
uv run phoneagent "打开微信，然后搜索联系人张三"
```

指定设备：

```bash
uv run phoneagent \
  --device-id emulator-5554 \
  "打开 Chrome，然后搜索 PhoneAgent"
```

交互模式：

```bash
uv run phoneagent
```

## 应用解析与别名

PhoneAgent 会动态查询设备上的 Launcher Activity，并将真实 package/activity 作为确定性依据。由于 Android Shell 无法在所有系统版本上稳定获得应用显示名，未知应用可能需要用户别名。

支持两种 JSON 格式：

```json
{
  "力扣": "com.lingkou.leetcode",
  "相机": "com.example.camera"
}
```

或者：

```json
{
  "com.lingkou.leetcode": ["力扣", "LeetCode"],
  "com.example.camera": ["相机", "Camera"]
}
```

使用：

```bash
uv run phoneagent --app-aliases-file app_aliases.json "打开相机"
```

## 验证语义

每个动作结果至少包含以下字段：

```json
{
  "command_success": true,
  "observable_effect_verified": true,
  "semantic_effect_verified": null
}
```

含义：

- `command_success`：ADB/Android 执行层接受了命令。
- `observable_effect_verified`：检测到前台应用变化或超过阈值的画面变化。
- `semantic_effect_verified`：确定性系统状态足以证明动作语义，例如目标 package 已经位于前台。

对普通坐标点击，`semantic_effect_verified` 通常为 `null`，因为画面变化不等于点击目标正确。

验证状态包括：

- `passed`
- `failed`
- `inconclusive`
- `skipped`

## 恢复策略

默认恢复是保守且有界的：

- `REPLAN`：向模型提供失败证据，选择不同策略。
- `REOBSERVE`：获取新的可信截图。
- `RETRY_ACTION`：只对 `Launch`、`Wait`、`Home` 等少量幂等动作进行一次有界重试。
- `RELAUNCH`：目标应用前台不匹配时重新启动。
- `TAKEOVER`：请求用户处理受保护或敏感页面。
- `ABORT`：恢复预算耗尽或遇到不可恢复失败。

`Back`、`Tap`、`Type`、`Swipe`、`Double Tap` 和 `Long Press` 不会被运行时盲目自动重放。

`BACKTRACK` 与 `HOME_RESET` 默认关闭，只能显式启用：

```bash
uv run phoneagent \
  --enable-backtrack-recovery \
  --enable-home-reset-recovery \
  "执行任务"
```

## 轨迹记录

默认轨迹保存在 `runs/trajectory_<run_id>.json`，采用临时文件加原子替换写入。

轨迹包含：

- 任务和运行时间；
- 状态机迁移；
- 截图尺寸、hash 和当前前台应用；
- 模型响应与 token/延迟指标；
- 解析后的动作；
- 命令执行结果；
- 验证证据；
- 恢复决策与结果；
- 最终状态。

轨迹默认不直接保存原始截图二进制，但可能包含任务文本、模型输出、应用名称和执行元数据。公开轨迹前请自行脱敏。

## Python API

```python
from phoneagent import AgentConfig, PhoneAgent, RecoveryConfig, VerificationConfig

agent = PhoneAgent(
    agent_config=AgentConfig(
        verification=VerificationConfig(
            enabled=True,
            observation_retries=1,
            visual_change_threshold=0.002,
        ),
        recovery=RecoveryConfig(
            enabled=True,
            max_total_recoveries=8,
            max_attempts_per_failure=2,
            allow_backtrack=False,
            allow_home_reset=False,
        ),
    )
)

message = agent.run("打开设置并进入 Wi-Fi 页面")
print(message)
print(agent.state.phase.value)
print(agent.state.last_verification)
print(agent.last_trajectory_path)
```

导入 `phoneagent` 不会自动加载 `.env`、连接设备或初始化模型。CLI 入口会在导入运行时模块前显式加载当前项目的 `.env`。

## 开发

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run python -m build
```

测试不要求连接真实 Android 设备。真实设备测试仍建议在发布前单独执行。

## 安全说明

PhoneAgent 可以操作真实设备并触发外部副作用。请勿在缺少人工监督的情况下用于支付、转账、删除数据、发送敏感信息或其他高风险任务。

发现安全问题请参阅 [SECURITY.md](SECURITY.md)。

## 路线图

后续工作将基于真实 trajectory 渐进推进：

1. 任务级/子目标级语义验证；
2. 更可靠的应用名称发现与设备兼容性；
3. 可复现的真实设备评测集；
4. Android 原生执行端与端侧部署；
5. 隐私、权限和用户可控性设计。

## License

本项目采用 [Apache License 2.0](LICENSE)。
