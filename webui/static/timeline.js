"use strict";

const eventLabels = {
  start: "任务开始",
  phase_change: "进入新阶段",
  observation: "观察手机屏幕",
  model_request: "请求模型规划",
  model_response: "模型完成规划",
  action: "生成操作",
  execution: "执行操作",
  verification: "验证操作结果",
  recovery: "调整执行策略",
  finish: "任务结束",
  error: "发生错误",
  note: "记录信息",
  user_prompt: "等待用户",
  user_response: "用户已响应",
  web_task_started: "任务已提交",
  web_task_finished: "任务已结束",
  web_task_error: "任务异常",
  web_task_cancel_requested: "请求停止任务",
};

export function truncate(text, length = 46) {
  const value = String(text || "").trim();
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function formatTime(timestamp) {
  if (!timestamp) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date(timestamp * 1000));
}

function eventKind(type) {
  if (["error", "web_task_error"].includes(type)) return "error";
  if (["recovery"].includes(type)) return "recovery";
  if (["verification"].includes(type)) return "verification";
  if (["action", "execution"].includes(type)) return "action";
  if (["finish", "web_task_finished"].includes(type)) return "finish";
  return "neutral";
}

function eventGlyph(type) {
  return {
    error: "!", recovery: "↻", verification: "✓", action: "→", finish: "◆", neutral: "·",
  }[eventKind(type)];
}

function summarizeEvent(event) {
  const payload = event.payload || {};
  if (event.type === "phase_change") return payload.reason || event.message;
  if (event.type === "action") {
    const action = payload.action || {};
    return action._metadata === "finish"
      ? action.message || event.message
      : `${action.action || "Action"}${action.description ? ` · ${action.description}` : ""}`;
  }
  if (event.type === "model_response") {
    return truncate(payload.thinking || payload.raw_content || event.message, 220);
  }
  if (event.type === "verification") return payload.message || event.message;
  if (event.type === "recovery") {
    return payload.reason || payload.message || payload.decision?.reason || event.message;
  }
  if (event.type === "observation") {
    return payload.current_app ? `当前应用：${payload.current_app}` : event.message;
  }
  return event.message || eventLabels[event.type] || event.type;
}

export function timelineEvents(events) {
  const hidden = new Set(["startup", "startup_ready", "startup_failed", "model_request"]);
  return events.filter((event) => !hidden.has(event.type));
}

export function processEvents(events) {
  const visible = new Set([
    "observation", "model_response", "action", "execution", "verification", "recovery", "error",
  ]);
  return events.filter((event) => visible.has(event.type));
}

export function latestProcessText(events, task) {
  if (task?.status === "cancelling") return "正在安全停止当前任务…";
  if (task?.status === "waiting_user") return "需要你的确认或手机操作，Agent 正在等待。";
  if (["success", "failed", "cancelled"].includes(task?.status)) {
    return task.result || task.error || "执行过程已经结束。";
  }
  const modelResponse = [...events].reverse().find((event) => event.type === "model_response");
  const modelContent = modelResponse?.payload?.raw_content
    || modelResponse?.payload?.thinking
    || modelResponse?.message;
  if (modelContent) return truncate(modelContent, 260);
  const latest = processEvents(events).at(-1);
  if (latest) return truncate(summarizeEvent(latest), 260);
  return "已收到任务，正在等待第一条执行记录…";
}

export function renderTimeline(events, target, { live = false, waitingText = null } = {}) {
  const visible = timelineEvents(events).slice(-250);
  target.replaceChildren();
  visible.forEach((event) => {
    const item = document.createElement("article");
    item.className = "timeline-item";
    item.dataset.kind = eventKind(event.type);
    const marker = document.createElement("span");
    marker.className = "timeline-marker";
    marker.textContent = eventGlyph(event.type);
    const body = document.createElement("div");
    body.className = "timeline-body";
    const head = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = eventLabels[event.type] || event.type;
    const meta = document.createElement("span");
    const step = Number.isInteger(event.step) ? event.step : event.payload?.step;
    meta.textContent = `${Number.isInteger(step) ? `第 ${step} 步 · ` : ""}${formatTime(event.timestamp)}`;
    head.append(title, meta);
    const summary = document.createElement("p");
    summary.textContent = summarizeEvent(event);
    body.append(head, summary);
    if (event.type === "model_response") {
      const raw = event.payload?.raw_content || event.payload?.thinking;
      if (raw) {
        const details = document.createElement("details");
        const toggle = document.createElement("summary");
        const pre = document.createElement("pre");
        toggle.textContent = event.payload?.protocol_error ? "查看被拒绝的模型输出" : "查看模型原文";
        pre.textContent = raw;
        details.append(toggle, pre);
        body.append(details);
      }
    }
    item.append(marker, body);
    target.append(item);
  });
  if (live) {
    const waiting = document.createElement("div");
    waiting.className = "timeline-waiting";
    const spinner = document.createElement("i");
    const text = document.createElement("span");
    text.textContent = waitingText || "等待下一步执行…";
    waiting.append(spinner, text);
    target.append(waiting);
  } else if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "没有可显示的执行记录";
    target.append(empty);
  }
}
