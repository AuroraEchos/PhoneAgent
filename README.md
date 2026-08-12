# PhoneAgent

[![CI](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml)

[![Release](https://img.shields.io/github/v/release/AuroraEchos/PhoneAgent)](https://github.com/AuroraEchos/PhoneAgent/releases)

[![License](https://img.shields.io/github/license/AuroraEchos/PhoneAgent)](LICENSE)

[English](README_EN.md) | 简体中文

[项目主页](https://auroraechos.github.io/PhoneAgent/) · [GitHub](https://github.com/AuroraEchos/PhoneAgent)

PhoneAgent 是一个面向真实 Android 设备的视觉语言智能体研究与评测运行时
（Research Runtime / Evaluation Runtime）。

它通过屏幕观察、视觉语言模型推理、严格动作协议、ADB 执行和结果验证，让研究者可以用
自然语言驱动手机任务，并获得可复现、可审计的执行证据。

核心执行流程：

```text
Observe → Plan → Execute → Verify → Recover → Repeat
```

项目当前明确收敛于研究和评测基础设施，重点是可靠性、可解释失败和稳定轨迹，不追求横向
增加工作流框架或应用特化能力。

## 核心能力

- 基于截图的视觉理解和任务规划。
- 只执行响应末尾唯一且完整的 `do(...)` 或 `finish(...)` 调用；它前面的文本仅作为
  思考记录，不接受 XML、JSON、代码块、多个调用、尾随文本或残缺输出。
- 默认要求模型正文只包含动作调用；首次协议错误会在同一 Agent step 内进行一次受限的
  action-only 重试，不触碰设备，也不计作恢复。
- 明确入口应用的任务会在首次观察后优先确定性启动；其他 `Launch` 仍按需解析别名、检查安装状态并验证前台包名。
- 支持动作执行后的状态验证。
- 通知与控制中心使用语义动作：优先执行 `cmd statusbar`，打开无效时由执行层自动使用左上角或右上角下拉手势兜底，并将内部尝试写入轨迹。
- 中断信号可关闭当前模型流并提前结束 Wait；已发送的原子 ADB 命令完成后不会再执行下一步。
- 坐标动作在用户确认后、ADB 下发前重新观察屏幕；目标区域或页面结构变化时取消旧动作，
  以新截图重新规划，并在轨迹中记录零触摸的 precondition 冲突。
- 使用排除系统栏的主体区域指纹判断页面停滞，并仅对真实坐标动作进行坐标重复检测。
- 只使用重新规划、重新观察、安全动作重试、人工接管和终止五类有界恢复。
- `AgentState.phase` 提供唯一实时阶段，统一 `AgentEvent` 记录完整审计历史。
- 自动保存结构化执行轨迹，便于调试、回归分析和后续评测。

## 运行时边界

- 模型文本不会作为 Python 代码执行；动作必须通过 AST、白名单和参数校验。
- 协议错误进入 strict-action recovery，不会尝试提取多个动作或修补字符串。
- 动作参数采用封闭 Schema：未知字段、重复关键字和缺失的必需参数均在执行前拒绝。
- 只有 `Launch`、`Wait`、`Home` 可在无敏感标记时进行一次安全重试。
- `Tap`、`Type`、`Swipe`、`Back` 等动作不会被自动重放。
- `Tap`、`Double Tap`、`Long Press` 和 `Swipe` 默认启用执行前截图新鲜度守卫；仅诊断时
  可使用 `--disable-pre-action-freshness` 关闭。
- 当前状态只保存运行所需的最新值；模型原文、思考、动作、验证和阶段历史以 trajectory
  event stream 为准。

## 致谢

PhoneAgent 的早期开发受到开源项目 [zai-org/Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 的启发。

感谢智谱 AI 团队开源 Open-AutoGLM，并提供了面向手机 Agent 的探索方向。

同时，PhoneAgent 推荐使用智谱 BigModel 提供的视觉语言模型作为默认推理服务。

## 环境要求

目前推荐环境：

- Ubuntu Linux
- Python 3.12+
- Android Platform Tools (`adb`)
- 一台开启 USB 调试的 Android 手机
- 一个支持视觉输入的 VLM API

## Android 设备准备

### 1. 安装 ADB

Ubuntu:

```bash
sudo apt install adb
```

检查：

```bash
adb version
```

如果输出类似：

```text
Android Debug Bridge version 1.0.xx
```

说明安装成功。

### 2. 开启手机 USB 调试

手机：

```
设置
 → 关于手机
 → 连续点击版本号 7 次
 → 开发者选项
 → 开启 USB 调试
```

连接手机：

```bash
adb devices
```

第一次连接时，需要在手机上允许 USB 调试授权。

正常输出：

```text
List of devices attached

xxxxxxxx	device
```

说明 PhoneAgent 可以访问设备。

### 3. 安装 ADB Keyboard（推荐）

PhoneAgent 推荐安装：

https://github.com/senzhk/ADBKeyBoard

用于稳定输入：

- 中文
- 特殊字符
- 长文本

## 安装 PhoneAgent

推荐使用 uv：

安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

下载项目：

```bash
git clone https://github.com/AuroraEchos/PhoneAgent.git

cd PhoneAgent
```

安装依赖：

```bash
uv sync --extra dev
```

创建配置：

```bash
cp .env.example .env
```

## 配置模型 API

PhoneAgent 兼容 OpenAI Chat Completions API。

推荐使用：

### 智谱 BigModel

文档：

https://docs.bigmodel.cn/cn/api/introduction

配置：

```dotenv
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL=autoglm-phone
API_KEY=你的API_KEY
```

API Key 可以在智谱开放平台申请。

## 检查安装

查看版本：

```bash
uv run phoneagent --version
```

查看帮助：

```bash
uv run phoneagent --help
```

检查设备：

```bash
uv run phoneagent --list-devices
```

查看静态别名表中已配置且当前设备已安装的应用：

```bash
uv run phoneagent --list-apps
```

## 基本使用

简单任务：

```bash
uv run phoneagent "打开设置"
```

多步骤任务：

```bash
uv run phoneagent "打开微信，然后搜索联系人张三"
```

指定设备：

```bash
uv run phoneagent \
  --device-id YOUR_DEVICE_ID \
  "打开浏览器搜索 PhoneAgent"
```

## Web Console

如果希望在浏览器里提交任务、查看实时事件和调试轨迹，可以启动独立的本地 Web Console：

```bash
uv run phoneagent-web --open-browser
```

默认地址：

```text
http://127.0.0.1:8765
```

Web 服务启动后会完成一次设备与模型 API 预检，并在该服务进程存活期间复用同一个
PhoneAgent 运行时。后续连续提交任务不会重复检查。页面直接消费统一 `AgentEvent`，
可以显示实时阶段、模型响应、动作、验证与恢复，处理敏感操作确认和人工接管，并浏览或
下载 `runs/trajectory_*.json`。

详细说明见 [`webui/README.md`](webui/README.md)。控制接口没有身份认证，建议保持默认的
`127.0.0.1` 监听地址，不要直接暴露到局域网或公网。

## 应用启动别名

PhoneAgent 不会在任务开始时扫描或缓存设备应用目录。首次观察后，运行时会保守识别任务中
“打开微信”“在支付宝里”或“微信小程序”这类明确入口，并通过
[`src/phoneagent/config/apps.py`](src/phoneagent/config/apps.py) 的静态兼容表让 `Launch` 成为
第一个设备动作；若目标已经在前台则不会重复启动。模型后续输出的 `Launch` 也使用同一套
按需解析、安装检查、ADB 启动和前台包名验证流程。入口启动失败时，结构化错误会交还模型，
允许其改用可见 GUI 路径。

```bash
# 查看所有内置名称和别名
uv run phoneagent --list-configured-apps

# 查看别名表中当前设备已安装的包
uv run phoneagent --list-apps
```

需要支持新的常用名称时，可以向 `APP_PACKAGES` 添加别名。未配置的已安装应用不会自动
出现在模型上下文中；此时可以让模型使用准确 package，或者通过普通视觉 GUI 路径操作。

## Python API

```python
from phoneagent import PhoneAgent

agent = PhoneAgent()

result = agent.run(
    "打开设置并进入 Wi-Fi 页面"
)

print(result)
```

## 轨迹记录

每次运行会生成：

```text
runs/trajectory_xxxxx.json
```

轨迹中的事件流记录：

- 阶段迁移
- 模型请求
- Agent 动作
- 执行结果
- 验证信息
- 恢复过程

`AgentState` 快照只表示任务结束时的最终状态，事件流是阶段和执行历史的权威来源。

## 评测报告

运行时接受 `finish(success=True)` 并不等于任务在真实设备上语义正确。完成实机任务并进行
人工或确定性判定后，可以汇总 trajectory：

```bash
uv run phoneagent-eval runs \
  --annotations evaluation/annotations.json \
  --output evaluation/report.json
```

报告严格区分运行时自报成功率和外部判定的任务成功率，同时汇总步数、恢复、错误码、模型
耗时与 Token。评测流程和标注格式见 [`docs/EVALUATION.md`](docs/EVALUATION.md)，发布前的
真机回归步骤和记录表见 [`docs/REAL_DEVICE_REGRESSION.md`](docs/REAL_DEVICE_REGRESSION.md)。
v0.2.0 的首轮脱敏真机结果见
[`docs/REAL_DEVICE_RESULT_v0.2.0.md`](docs/REAL_DEVICE_RESULT_v0.2.0.md)。

如果要系统理解项目设计、准备简历描述和技术面试，可以从
[`docs/INTERVIEW_GUIDE.md`](docs/INTERVIEW_GUIDE.md) 开始。

## 开发

```bash
uv sync --extra dev

uv run pytest -q

uv run ruff check .
```

## 当前限制

PhoneAgent 当前仍然是研究原型：

- 需要通过 ADB 连接 Android 设备。
- 人类可读的 `Launch` 名称受内置静态别名表限制；未收录应用需要准确 package 或普通
  视觉 GUI 路径。
- 坐标点击的语义正确性仍依赖视觉模型。
- 尚未完成 Android 原生端侧部署。

## License

Apache License 2.0
