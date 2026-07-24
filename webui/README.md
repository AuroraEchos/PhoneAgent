# PhoneAgent Web Console

这是一个与 `src/phoneagent` 核心运行时分离的本地调试界面。它只依赖 Python 标准库和
PhoneAgent 已有依赖，不需要 Node.js，也不需要修改或重新构建前端资源。

## 启动

先完成 PhoneAgent 的正常安装和 `.env` 配置，然后在仓库根目录运行：

```bash
uv run phoneagent-web --open-browser
```

如果不希望自动打开浏览器：

```bash
uv run phoneagent-web
```

浏览器访问：

```text
http://127.0.0.1:8765
```

自定义端口：

```bash
uv run phoneagent-web --port 9000
```

## 会话行为

Web 服务每次启动会执行一轮与 CLI 一致的检查：

1. ADB 可执行文件
2. 已连接并授权的 Android 设备
3. ADB Keyboard
4. 截图与视觉观察
5. 视觉模型 API

检查通过后创建一个 PhoneAgent 实例。只要 Web 服务进程没有退出，后续任务都会复用
这个实例和检查结果；刷新或重新打开浏览器不会触发检查。只有手动点击“重新检查”，或
停止并重启服务时，才会创建新的检查会话。

当前版本一次只执行一个任务。这样可以避免两个 Agent 线程同时控制同一台手机。

## 页面功能

- 提交自然语言任务并查看当前阶段、步数、前台应用和恢复次数
- 实时查看模型响应、结构化动作、执行、验证和恢复事件
- 分别展示 `command_success`、可观察结果和确定性语义证据
- 在浏览器中确认敏感操作
- 在需要验证码、密码或受保护页面时等待人工接管
- 浏览、搜索、查看并下载 `runs/trajectory_*.json`

轨迹仍由 PhoneAgent 核心运行时写入，Web Console 只读取并展示，不改变 schema。

## 配置

设备、模型和运行时参数继续读取仓库根目录的 `.env`。Web Console 额外支持：

```dotenv
PHONE_AGENT_WEB_HOST=127.0.0.1
PHONE_AGENT_WEB_PORT=8765
```

也可以通过命令行的 `--host` 和 `--port` 覆盖。

## 安全说明

Web Console 能够控制已连接的 Android 设备，并能读取包含任务、动作和模型输出的轨迹。
当前服务不包含登录或权限系统，因此默认只监听 `127.0.0.1`。不要直接绑定公网地址；
如果确实需要远程访问，应自行增加反向代理、TLS 和身份认证。
