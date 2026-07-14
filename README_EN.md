# PhoneAgent



[![CI](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/AuroraEchos/PhoneAgent/actions/workflows/ci.yml)

[![Release](https://img.shields.io/github/v/release/AuroraEchos/PhoneAgent)](https://github.com/AuroraEchos/PhoneAgent/releases)

[![License](https://img.shields.io/github/license/AuroraEchos/PhoneAgent)](LICENSE)

[简体中文](README.md) | English

[项目主页](https://auroraechos.github.io/PhoneAgent/) · [GitHub](https://github.com/AuroraEchos/PhoneAgent)

PhoneAgent is a面向真实 Android 设备的vision-language agent runtime（Vision-Language Agent Runtime）。

它通过屏幕观察、视觉语言模型推理、结构化动作执行和结果验证，让用户可以使用自然语言控制手机完成任务。

核心执行流程：

```text
Observe → Plan → Execute → Verify → Recover → Repeat
```

PhoneAgent 当前定位为一个开源研究与工程原型，重点探索可靠、可审计的手机 GUI Agent 执行链路。

## 核心能力

- 基于截图的视觉理解和任务规划。
- 使用结构化 Action Protocol 执行动作，而不是执行模型生成代码。
- 支持 Android 应用发现和确定性启动。
- 支持动作执行后的状态验证。
- 支持有限恢复和重新规划。
- 自动记录 Agent 执行轨迹，方便调试和分析。

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
PHONE_AGENT_BASE_URL=https://open.bigmodel.cn/api/paas/v4
PHONE_AGENT_MODEL=autoglm-phone
PHONE_AGENT_API_KEY=你的API_KEY
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

查看可启动应用：

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

## 应用别名

部分 Android 系统无法稳定获取应用显示名称。

可以通过 alias 文件：

```json
{
  "微信": "com.tencent.mm",
  "淘宝": "com.taobao.taobao"
}
```

运行：

```bash
uv run phoneagent \
  --app-aliases-file app_aliases.json \
  "打开微信"
```

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

记录：

- 当前状态
- 模型请求
- Agent 动作
- 执行结果
- 验证信息
- 恢复过程

方便调试和研究。

## 开发

```bash
uv sync --extra dev

uv run pytest -q

uv run ruff check .
```

## 当前限制

PhoneAgent 当前仍然是研究原型：

- 需要通过 ADB 连接 Android 设备。
- 部分应用需要配置 alias。
- 坐标点击的语义正确性仍依赖视觉模型。
- 尚未完成 Android 原生端侧部署。

## License

Apache License 2.0
