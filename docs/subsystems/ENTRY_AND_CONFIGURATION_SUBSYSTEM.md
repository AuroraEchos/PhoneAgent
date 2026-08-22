# PhoneAgent Entry & Configuration Subsystem（入口与配置子系统）

本文依据 [`entrypoint.py`](../../src/phoneagent/entrypoint.py)、[`cli.py`](../../src/phoneagent/cli.py) 和 [`config`](../../src/phoneagent/config)，说明命令行参数、环境变量、预检、应用别名和运行时配置如何汇合为一次 PhoneAgent 任务。

## 1. 正式入口

`pyproject.toml` 注册：

```text
phoneagent      → phoneagent.entrypoint:main
phoneagent-web  → webui.server:main
phoneagent-eval → phoneagent.evaluation:main
```

`phoneagent` 的正式入口顺序是：

```text
entrypoint.main()
→ load_env()
→ 延迟 import phoneagent.cli
→ cli.main()
```

先加载 `.env` 再导入 CLI 很重要，因为 ModelConfig 和 TimingConfig 的部分默认值在实例化或模块导入时读取环境。

直接 `import phoneagent` 不会加载 `.env`、检查 ADB 或初始化模型。根包使用 `__getattr__` 懒加载小型公共 API，保持库导入无副作用。

## 2. `.env` 查找与优先级

`load_env()`：

1. 如果调用者给出路径，直接使用；
2. 否则从当前目录及其父目录查找 `.env`；
3. 在源码 checkout 中还会通过 `pyproject.toml` 定位仓库根；
4. 默认 `override=False`，已有真实环境变量优先；
5. 优先使用 python-dotenv，缺失时使用简单 KEY=VALUE parser。

简单 parser 忽略空行、注释和没有 `=` 的行，并去掉成对单/双引号。

库调用者若希望加载本地文件，必须显式调用 `load_env()`；这是有意的信任边界。

## 3. CLI 主分发

`cli.main()` 的分支顺序：

```text
parse_args
→ --list-configured-apps
→ --list-apps
→ connect/disconnect/enable-tcpip/list-devices
→ build CLIConfig
→ 设备预检
→ 模型预检
→ 创建 PhoneAgent
→ 单任务或交互模式
```

纯设备管理命令在要求模型配置之前处理，因此 `phoneagent --list-devices` 不需要 BASE_URL/MODEL/API_KEY。

## 4. CLI 配置对象

`CLIConfig` 聚合 ModelConfig、AgentConfig、device_id、task、是否跳过系统/模型检查和 quiet。

缺少 BASE_URL、MODEL 或 API_KEY 时，以配置错误退出。构造嵌套 Config 触发的 ValueError 也转换为配置错误。

### 4.1 常用公开参数

- task；
- `--base-url`、`--model`、`--apikey`、`--max-tokens`；
- `--max-steps`、`--max-runtime-seconds`；
- `--device-id`；
- `--disable-verification`；
- `--disable-recovery`；
- `--disable-pre-action-freshness`；
- `--disable-task-verification`；
- `--disable-action-risk-review`；
- `--trajectory-dir`；
- `--skip-system-check` / `--skip-model-check`；
- `--allow-fallback-screenshot`；
- `--quiet`。

关闭项主要用于诊断，会降低默认可靠性或安全保证。

### 4.2 隐藏高级参数

CLI 仍接受但不在 help 中显示：

- max consecutive failures / repeated actions；
- context turns；
- observation retries；
- protocol retries 与 retry max tokens；
- verification retries 与 threshold；
- max recoveries 与 attempts per failure。

它们通过 argparse default 读取对应环境变量。

## 5. 三组配置

### 5.1 `ModelConfig`

控制 endpoint、模型名、生成参数、超时、transport retry、usage 和 provider extra body。

### 5.2 `AgentConfig`

控制任务循环、上下文、设备、协议、观测、轨迹和嵌套的 Freshness/Verification/Recovery/SemanticReview。

### 5.3 `TimingConfig`

分为：

- `ActionTimingConfig`：键盘切换、清空、输入、恢复等待；
- `DeviceTimingConfig`：Tap、Double Tap、Long Press、Swipe、Back、Home、Launch 后等待；
- `ConnectionTimingConfig`：ADB/TCP 和 Server 重启等待。

所有 timing 环境值必须非负。全局 `TIMING_CONFIG` 可通过 `update_timing_config()` 替换三组子配置。

## 6. 设备管理命令

CLI 可以：

- `--connect ADDRESS`；
- `--disconnect [ADDRESS]`；
- `--enable-tcpip [PORT]`；
- `--list-devices`；
- `--list-apps`；
- `--list-configured-apps`。

`--list-apps` 必须选择唯一 ready device，并返回配置表与已安装包的交集。`--list-configured-apps` 只打印静态别名，不访问设备。

## 7. Android/ADB 预检

`check_system_requirements()` 执行四项：

### 7.1 ADB executable

使用 `shutil.which("adb")` 并执行 `adb version`。

### 7.2 Connected device

列出所有设备及状态。显式 device_id 必须处于 `device` 状态；未指定时必须恰好有一个 ready device。

### 7.3 ADB Keyboard

检查 ADB Keyboard 是否安装和当前 IME。缺少键盘是 WARN：普通导航仍可运行，但 Type 会失败。

### 7.4 Visual observation

强制真实 screenshot，fallback=False；显示原始与编码尺寸；近乎均匀黑屏直接导致预检失败。

预检返回 `(success, resolved_device_id)`，解析出的 device_id 写回 AgentConfig。

## 8. 模型 API 预检

`check_model_api()` 创建同步 OpenAI client，发送非流式短请求：

```text
Reply with OK.
max_tokens=8
temperature=0
```

没有 choices 或 content/reasoning 都为空时失败。某些 reasoning 模型可能因为短 Token 限制只返回 reasoning_content；这种情况记录 WARN 但认为 endpoint 可访问。

预检只证明 API 能响应，不证明它能正确理解截图或遵循 Action Protocol。

## 9. 应用别名配置

[`config/apps.py`](../../src/phoneagent/config/apps.py) 保存人类名称到 Android package 的静态表。

`get_package_name()` 的匹配顺序：

1. 原始 alias 精确匹配；
2. 忽略大小写与所有空白的标准化匹配；
3. 输入看起来像 Android package 时直接接受；
4. 否则返回 None，不猜测未知名称。

同一 package 第一个注册的 alias 是 canonical display name。返回映射时使用副本，调用者不能修改内部表。

## 10. 任务入口应用推断

`infer_task_entry_app(task)` 不是任意实体识别。应用名必须与明确语境关联：

- 打开、启动、进入、使用、登录等动作；
- “在某应用中/里”的操作容器；
- 英文 open/launch/use；
- 微信或支付宝的小程序容器；
- 明确 package name。

候选按规则分数、出现位置和 alias 长度排序。否定词在同一近邻 clause 中会排除匹配。仅提及应用名不会触发确定性启动。

Agent 只在首步使用该结果，并在目标包已经前台时跳过 Launch。

## 11. 任务执行和退出码

CLI 退出码：

| 值 | 含义 |
| ---: | --- |
| 0 | CLI 操作或 Agent 任务成功 |
| 1 | 设备、模型、命令或未处理运行错误 |
| 2 | 配置错误 |
| 3 | Agent 正常运行但任务最终失败 |

有 task 时执行一次并打印 phase、recoveries 和 trajectory path。没有 task 时进入交互循环，支持 exit、quit、q；同一个 PhoneAgent 实例可连续执行多个任务，每次 run 会初始化新的状态和轨迹。

## 12. CLI 与 Web 配置差异

Web Console 不调用 CLI argparse，而由 `webui.runtime._build_configs()` 从 `.env` 直接构建 ModelConfig 和 AgentConfig。两条入口复用相同配置类型，但暴露的开关不同。

Web 当前从环境读取主要循环、验证阈值、恢复预算、任务完成审核、动作风险审核和 Token 单价；Freshness 使用 AgentConfig 的默认启用配置。

## 13. 当前限制

1. 应用表是静态配置，不是动态完整 catalog；
2. 入口应用推断依赖中英文正则，宁可漏判也不凭提及强制启动；
3. CLI 与 Web 配置组装代码不是同一个函数，新增配置时需要同步维护；
4. 模型短预检不验证视觉输入和动作协议；
5. `--skip-*` 和 disable flags 可绕过默认保护，只适合诊断；
6. 通过 `python -m phoneagent.cli` 直接进入 CLI 不会经过正式 entrypoint 的自动 `.env` 加载。

## 14. 阅读顺序与测试

1. `entrypoint.main()` 与根包 lazy API；
2. `load_env()`；
3. CLI `main()` 和 argparse；
4. `_build_cli_config()`；
5. 设备和模型预检；
6. apps alias 与 `infer_task_entry_app()`；
7. TimingConfig；
8. `_run_agent()`、单任务和交互模式。

```bash
uv run pytest tests/test_env.py -q
uv run pytest tests/test_app_resolution.py tests/test_apps.py -q
uv run phoneagent --help
```
