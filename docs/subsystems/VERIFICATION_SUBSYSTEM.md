# PhoneAgent Verification Subsystem（动作效果验证子系统）

本文依据 [`runtime/verification.py`](../../src/phoneagent/runtime/verification.py) 和 Agent 的执行后调用路径，说明 PhoneAgent 如何在设备动作之后收集证据，以及为什么“ADB 命令成功”不能直接等价于“动作和任务成功”。

## 1. 三种不同事实

Verification 明确分离：

```text
command_success
observable_effect_verified
semantic_effect_verified
```

- `command_success`：执行层是否接受并完成 Android/ADB 调用；
- `observable_effect_verified`：是否观察到确定性系统状态或视觉变化；
- `semantic_effect_verified`：证据是否能证明这个动作类型的语义效果。

普通 Tap 后屏幕变化，可以证明有可观察效果，却不能证明点中了语义正确的按钮，因此 `semantic_effect_verified=None`。

任务级成功更高一层，由 Semantic Review 和外部 benchmark annotation 处理。

## 2. 数据模型

### 2.1 `VerificationStatus`

| 状态 | 含义 |
| --- | --- |
| `PASSED` | 当前策略获得足够证据 |
| `FAILED` | 明确失败，需要恢复 |
| `INCONCLUSIVE` | 没有对应策略或证据不能下结论 |
| `SKIPPED` | 显式跳过，但不声称效果成立 |

`VerificationResult.passed` 对 PASSED 和 SKIPPED 返回 True，表示运行时无需因这次验证进入恢复；这不意味着 SKIPPED 声称语义成功。

### 2.2 `VerificationResult`

包含 status、policy、message、三层成功字段、screen/app change、视觉差异比例、error_code 和 metadata。

`verification_enabled` 通过 policy 是否为 `verification_disabled` 判断，而不是单独保存布尔字段。

## 3. 配置

`VerificationConfig` 默认：

| 配置 | 默认值 |
| --- | ---: |
| `enabled` | True |
| `settle_delay_seconds` | 0.15 s |
| `observation_retries` | 1 |
| `observation_retry_delay` | 0.35 s |
| `visual_change_threshold` | 0.002 |
| `image_compare_size` | 128 |
| `crop_top_ratio` / `crop_bottom_ratio` | 0.04 / 0.04 |

配置验证等待、重试、阈值、图像尺寸和裁剪范围。

## 4. Agent 的执行后流程

`_verify_action_once_async()`：

```text
execution.success=False
→ 不截图，直接按命令失败验证

execution.success=True
→ 进入 VERIFYING
→ Note/Call_API 以外的动作等待 settle delay
→ 获取 after observation
→ 拒绝不可用或空白截图
→ 记录 observation 并缓存给下一步
→ ActionVerifier.verify(before, after)
→ 记录 VERIFICATION 事件
```

Note 和 Call_API 不需要设备屏幕效果，因此不获取 after screenshot。

如果后置观测失败，命令可能已经执行，所以结果保留 `command_success=True`，同时返回 `verification_observation_failed`。这类状态不能盲目重放有副作用动作。

## 5. 总体短路顺序

`ActionVerifier.verify()` 依次判断：

1. execution 失败；
2. finish；
3. verification 全局禁用；
4. 不要求屏幕效果的 Note / Call_API；
5. after observation 缺失；
6. 计算公共视觉和应用证据；
7. 按动作类型应用专用策略；
8. 没有策略时返回 INCONCLUSIVE。

在正常 Agent 主路径中，finish 会在执行层作为终止动作处理，不进入普通 post-action verification；成功 finish 在此之前还会经过任务完成复核。Verifier 中保留 finish policy 使独立调用语义完整。

## 6. 视觉差异计算

执行前后截图解码为灰度图，默认裁掉顶部、底部各 4%，缩放到 `128 × 128`，计算平均像素绝对差异并归一化到 0..1。

如果 sha256 完全相同，差异直接为 0。图像解码失败但两端有 sha256 时，摘要不同保守返回 1.0，相同返回 0；都不可用时返回 None。

前台 app/package 变化或差异达到 0.002，都令 `screen_changed=True`。

### 6.1 系统区域例外

普通动作忽略状态栏和导航栏变化，避免时钟、信号图标等造成假阳性。但以下情况比较整屏：

- OpenNotifications / OpenQuickSettings / CloseSystemPanel；
- element/start/end 的 y 坐标落入配置的顶部或底部系统区域。

## 7. 动作专用策略

### 7.1 命令失败

任何 `execution.success=False` 都返回 FAILED：

```text
policy=command_success
command_success=False
observable_effect_verified=False
semantic_effect_verified=False
```

### 7.2 Verification 被禁用

返回 SKIPPED，command_success=True，但两类 effect 都是 None。该选项只用于诊断。

### 7.3 Note 与 Call_API

返回 PASSED、policy=`command_only`。它们不要求设备屏幕变化；执行回调成功就是其动作级语义结果，因此 semantic_effect_verified=True。

### 7.4 Launch

优先从 execution metadata 取得解析后的 package，否则使用 action.app；再与 after 的 current package/app 比较。

匹配时：

```text
policy=foreground_app_match
semantic_effect_verified=True
```

不匹配时返回 `verification_app_mismatch`。

### 7.5 Home

只有 after.current_app 严格为 `System Home` 才通过，否则返回 `verification_home_failed`。

### 7.6 系统面板

OpenNotifications / OpenQuickSettings 优先要求 `after.system_panel_visible=True`。如果面板状态未知，则只有焦点包看起来是 SystemUI/control center 且屏幕变化时才能通过。

失败返回 `verification_system_panel_not_open`。

CloseSystemPanel 在 `after.system_panel_visible=False` 时通过，即使原本已关闭也可幂等成功。如果 after 状态未知，但 before 明确可见、after 不再是系统面板且屏幕变化，也可通过。否则返回 `verification_system_panel_not_closed`。

### 7.7 Wait

Wait 在有可信后置观测时返回 `timed_wait_completed`，semantic_effect_verified=True，表示“有界等待动作完成”，并不要求画面变化。

### 7.8 Take_over 与 Interact

只要求人工交互后能取得可信观测，policy=`post_observation_available`，两类 effect 为 None。

### 7.9 Tap、Double Tap、Long Press、Swipe、Type、Back

这些动作只按前台应用或视觉变化验证：

- 有变化：PASSED，observable=True，semantic=None；
- 无变化：FAILED，`verification_no_effect`。

Type 后文本是否正确、Tap 是否点中正确控件，都不能从通用像素变化算法中得到确定语义证明。

### 7.10 未知策略

返回 INCONCLUSIVE 和 `verification_inconclusive`，而不是默认通过。

## 8. 系统面板 fallback

`PhoneAgent._verify_action_async()` 对两个打开面板动作增加一次内部 fallback：

```text
cmd statusbar 执行/验证失败
且错误为 system_panel_command_failed
或 verification_system_panel_not_open
→ 执行受控边缘手势
→ 再次观测和验证
```

primary 与 fallback 的 execution、verification、metadata 都保留在 `system_panel_attempts`。fallback 成功后更新原 execution 的最终 transport 和结果，模型只看到一个语义动作。

## 9. 内容签名与停滞检测

`visual_signature(observation)` 将截图裁掉系统区域、灰度化并缩放到 `128 × 128`，再计算 SHA-256。AgentState 用这个 `content_sha256` 优先判断相邻观测是否停滞。

因此状态栏时钟变化不会轻易把“应用内容没有变化”误判为新页面。签名失败时退回原 screenshot sha256。

## 10. Verification 与 Recovery

Verification 只陈述事实，不决定策略。常见映射为：

| Verification error | Recovery 倾向 |
| --- | --- |
| `verification_app_mismatch` | 首次安全 Launch 可重试，否则 REOBSERVE |
| `verification_no_effect` | 安全动作可重试，否则 REPLAN |
| `verification_observation_failed` | REOBSERVE |
| `protected_or_blank_screen` | TAKEOVER 或 ABORT |
| `verification_inconclusive` | REPLAN，不重放原动作 |

## 11. 当前限制

1. 通用视觉差异不理解 UI 语义；
2. 低阈值可能把合法动画当作动作效果，但仍不会声称 semantic=True；
3. 图像解码失败时 sha256 不同会保守视为最大变化，证据质量弱于真实像素比较；
4. OEM 系统面板识别依赖窗口标记；
5. 某些成功动作本来不会产生视觉变化，若没有专用策略可能被判 inconclusive；
6. Verification 只验证单个动作，不验证整项任务。

## 12. 阅读顺序与测试

1. `VerificationStatus`、`VerificationResult`；
2. `ActionVerifier.verify()` 的短路顺序；
3. 各动作 policy；
4. `_visual_difference_ratio()`；
5. 系统区域裁剪和 `visual_signature()`；
6. Agent 的 `_verify_action_once_async()`；
7. 系统面板 fallback；
8. `_evaluate_action_result_async()` 如何接入 Recovery。

```bash
uv run pytest tests/test_verification.py -q
uv run pytest tests/test_agent_loop.py -q -k 'verification or panel'
```
