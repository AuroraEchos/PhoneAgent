# PhoneAgent Freshness Subsystem（执行前观测新鲜度子系统）

本文依据 [`runtime/freshness.py`](../../src/phoneagent/runtime/freshness.py) 及其在 [`agent.py`](../../src/phoneagent/agent.py) 中的调用，说明 PhoneAgent 如何避免使用已经过期的截图坐标操作真实设备。

## 1. 问题定义

视觉 Agent 的动作不是在模型看到截图的瞬间执行：

```text
t0：截取规划截图
t1：上传模型
t2：模型推理
t3：可能等待用户确认
t4：发送 ADB 坐标动作
```

在 t0 到 t4 之间，广告、弹窗、视频、轮播图、键盘或前台应用都可能变化。Freshness Subsystem 实现的是乐观并发控制：动作仍绑定规划截图，但派发前重新取得当前截图，只有视觉前置条件兼容时才授权派发。

它验证的是“现在仍适合执行这个坐标”，不是“坐标语义一定正确”。

## 2. 适用动作

`ObservationFreshnessGuard.requires_check()` 只对以下标准动作返回 True：

```text
Tap · Double Tap · Long Press · Swipe
```

同时要求：

- FreshnessConfig.enabled=True；
- `_metadata == "do"`。

Launch、Type、Back、Home、Wait、系统面板语义动作和 finish 不经过这项坐标区域检查。

## 3. 配置

`FreshnessConfig` 的当前默认值：

| 配置 | 默认值 | 含义 |
| --- | ---: | --- |
| `enabled` | True | 是否启用 |
| `observation_retries` | 0 | 派发前新观测的额外重试次数 |
| `observation_retry_delay` | 0.1 s | 重试间隔 |
| `image_compare_width` | 256 | 比较图像的统一宽度 |
| `target_radius_x_ratio` | 0.10 | 目标区域横向半径 |
| `target_radius_y_ratio` | 0.05 | 目标区域纵向半径 |
| `pixel_delta_threshold` | 0.08 | 单像素视为变化的通道差异阈值 |
| `target_mean_difference_threshold` | 0.025 | 目标区域平均差异阈值 |
| `target_changed_pixel_ratio_threshold` | 0.15 | 目标区域变化像素比例阈值 |
| `global_mean_difference_threshold` | 0.15 | 全局平均差异阈值 |
| `global_changed_pixel_ratio_threshold` | 0.80 | 全局变化像素比例阈值 |
| `crop_top_ratio` / `crop_bottom_ratio` | 0.04 / 0.04 | 全局比较时忽略的系统区域 |

配置会验证重试值、图像宽度、所有比例的 `0..1` 范围、正目标半径，以及裁剪后是否仍保留足够画面。

## 4. `FreshnessResult`

结果同时保存结论与证据：

```text
checked / fresh / reason
planned_capture_age_seconds
fresh_capture_age_seconds
check_duration_seconds
app_changed / system_panel_changed / dimensions_changed
global_mean_difference / global_changed_pixel_ratio
target_mean_difference / target_changed_pixel_ratio
target_regions
comparison_error
```

截图年龄只进入审计证据，目前没有单独的“最大允许年龄”阈值。真正授权取决于身份、尺寸和视觉兼容性。

## 5. 判断顺序

`check(action, planned, current)` 按以下短路顺序运行：

### 5.1 当前观测可用性

当前截图不可用或全黑时：

```text
fresh=False
reason=fresh_observation_unusable
```

### 5.2 前台应用

优先比较 `current_package`，缺失时才使用 `current_app`，并统一 strip/casefold。身份变化直接拒绝，不继续依赖图片相似度。

### 5.3 系统面板状态

当面板状态从可见切换，或两端都有明确状态但不同，返回 `system_panel_state_changed`。Unknown 到 Unknown 不会被伪装成变化。

### 5.4 显示尺寸

比较真实 display width/height，缺失时退回编码图像尺寸。旋转、分辨率或显示尺寸变化返回 `display_dimensions_changed`。

### 5.5 完全相同截图

sha256 相同直接通过，四个差异指标置为 0，并记录目标点数量。

### 5.6 图像归一化

两张 Base64 图片解码为 RGB。宽高比差异超过 0.01 会抛出比较异常。之后统一缩放到配置宽度，按规划截图宽高比计算高度。

### 5.7 全局差异

全局图像先裁掉顶部和底部各 4%，减少时钟和导航条动画干扰，再计算：

- RGB 平均绝对差异，归一化到 0..1；
- 任一颜色通道超过 pixel delta 的像素比例。

### 5.8 目标区域差异

每个动作点周围建立矩形区域：横向半径为图宽 10%，纵向半径为图高 5%。

- Tap/Double Tap/Long Press：一个 element 区域；
- Swipe：start、end，以及两点中点，共三个区域。

多个区域取最大差异，保证滑动路径任一关键位置的大变化都能触发拒绝。

## 6. 阈值组合

目标区域使用 OR：

```text
target_mean >= 0.025
OR target_changed_ratio >= 0.15
→ target_region_changed
```

全局变化使用 AND：

```text
global_mean >= 0.15
AND global_changed_ratio >= 0.80
→ broad_screen_change_detected
```

这种差异是有意的：目标区域稍有明显变化就应该谨慎失效；全局变化只作为接近整屏替换的最后信号，不能因为动态 feed 或视频大范围移动就覆盖一个保持不变的目标按钮。

判断优先级为目标区域变化，再判断近乎整屏替换。两者都不满足时返回 `visual_precondition_compatible`。

任何解码、裁剪或比较异常都 fail closed：

```text
fresh=False
reason=freshness_comparison_failed
comparison_error=<异常类型与消息>
```

## 7. Agent 集成顺序

在 `_execute_accepted_action_async()` 中，坐标动作的顺序是：

```text
任务风险审核
→ 人工确认
→ _guard_action_freshness_async
→ ActionHandler.execute
```

人工确认必须先发生，因为用户等待期间界面最容易变化。

`_guard_action_freshness_async()`：

1. 使用 Freshness 自己的重试配置取得新观测；
2. 记录 source=`pre_action_freshness` 的 OBSERVATION；
3. 调用 guard.check；
4. 记录 PRECONDITION 事件；
5. fresh=True 时返回当前观测，并用它的真实显示尺寸执行；
6. fresh=False 时保存为 pending observation，进入结构化恢复。

失败事件始终记录：

```text
dispatch_authorized=False
command_dispatched=False
planned/current screenshot sha256
```

## 8. 错误和恢复

派发前无法取得观测：

```text
pre_action_observation_failed
```

Recovery 将它归为 observation error，选择 REOBSERVE。

取得观测但不兼容：

```text
pre_action_observation_changed
```

它属于不可重放错误，Recovery 选择 REPLAN。当前新截图已经保存，下一轮直接复用，不再发送旧动作。

成功的零触摸 replan 会结束当前失败 episode，不会因连续弹窗快速耗尽相同 failure key 的局部预算；总恢复次数和任务上限仍然生效。

## 9. 与 Verification 的区别

| Freshness | Verification |
| --- | --- |
| 动作派发前 | 动作派发后 |
| 比较规划截图与当前截图 | 比较执行前与执行后截图 |
| 判断旧动作是否仍可执行 | 判断动作是否产生可观察/语义效果 |
| 失败时 command_dispatched=False | 失败时命令通常已经发送 |
| 主要关注目标局部区域 | 主要关注动作类型对应的结果策略 |

## 10. 当前限制

1. 最后一次截图与 ADB 命令仍不是原子事务，存在很短的残余竞态；
2. 固定矩形目标区域不能理解控件边界；
3. 阈值是通用经验值，不按应用或设备自适应；
4. 局部动画恰好覆盖目标区域会保守拒绝；
5. 视觉相似只能证明前置条件兼容，不能证明 Planner 选择了正确控件；
6. 该检查不覆盖非坐标动作。

## 11. 阅读顺序与测试

1. `FreshnessConfig` 和 `FreshnessResult`；
2. `requires_check()`；
3. `check()` 的短路顺序；
4. `_difference_metrics()`；
5. `_target_points()` / `_target_boxes()`；
6. Agent 的 `_guard_action_freshness_async()`。

```bash
uv run pytest tests/test_freshness.py -q
uv run pytest tests/test_agent_loop.py -q -k freshness
```
