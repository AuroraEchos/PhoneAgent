"use strict";

const elements = {
  appSurface: document.querySelector("#appSurface"),
  preflightGate: document.querySelector("#preflightGate"),
  preflightCount: document.querySelector("#preflightCount"),
  preflightProgress: document.querySelector("#preflightProgress"),
  preflightState: document.querySelector("#preflightState"),
  preflightHelp: document.querySelector("#preflightHelp"),
  startupTitle: document.querySelector("#startupTitle"),
  startupMessage: document.querySelector("#startupMessage"),
  checkList: document.querySelector("#checkList"),
  recheckButton: document.querySelector("#recheckButton"),
  deviceIdentity: document.querySelector("#deviceIdentity"),
  modelIdentity: document.querySelector("#modelIdentity"),
  endpointIdentity: document.querySelector("#endpointIdentity"),
  reuseLabel: document.querySelector("#reuseLabel"),
  reuseNote: document.querySelector(".reuse-note"),
  historySidebar: document.querySelector("#historySidebar"),
  sidebarCollapse: document.querySelector("#sidebarCollapse"),
  sidebarClose: document.querySelector("#sidebarClose"),
  sidebarScrim: document.querySelector("#sidebarScrim"),
  mobileSidebarButton: document.querySelector("#mobileSidebarButton"),
  newTaskButton: document.querySelector("#newTaskButton"),
  trajectoryList: document.querySelector("#trajectoryList"),
  trajectorySearch: document.querySelector("#trajectorySearch"),
  refreshTrajectories: document.querySelector("#refreshTrajectories"),
  closeTrajectory: document.querySelector("#closeTrajectory"),
  trajectoryResult: document.querySelector("#trajectoryResult"),
  trajectoryTask: document.querySelector("#trajectoryTask"),
  trajectoryMeta: document.querySelector("#trajectoryMeta"),
  trajectoryEvents: document.querySelector("#trajectoryEvents"),
  downloadTrajectory: document.querySelector("#downloadTrajectory"),
  trajectoryUsagePanel: document.querySelector("#trajectoryUsagePanel"),
  trajectoryUsageSummary: document.querySelector("#trajectoryUsageSummary"),
  trajectoryUsageChart: document.querySelector("#trajectoryUsageChart"),
  trajectoryUsageNote: document.querySelector("#trajectoryUsageNote"),
  connection: document.querySelector(".connection-pill"),
  connectionLabel: document.querySelector("#connectionLabel"),
  sessionClock: document.querySelector("#sessionClock"),
  conversationTitle: document.querySelector("#conversationTitle"),
  conversationScroll: document.querySelector("#conversationScroll"),
  welcomeState: document.querySelector("#welcomeState"),
  threadView: document.querySelector("#threadView"),
  historyDetail: document.querySelector("#historyDetail"),
  taskStatus: document.querySelector("#taskStatus"),
  currentGoal: document.querySelector("#currentGoal"),
  workProcess: document.querySelector("#workProcess"),
  workProcessToggle: document.querySelector("#workProcessToggle"),
  workProcessDetails: document.querySelector("#workProcessDetails"),
  processTitle: document.querySelector("#processTitle"),
  processLatest: document.querySelector("#processLatest"),
  processNotice: document.querySelector("#processNotice"),
  eventFeed: document.querySelector("#eventFeed"),
  eventCount: document.querySelector("#eventCount"),
  taskResultPanel: document.querySelector("#taskResultPanel"),
  taskResult: document.querySelector("#taskResult"),
  taskUsagePanel: document.querySelector("#taskUsagePanel"),
  taskUsageSummary: document.querySelector("#taskUsageSummary"),
  taskUsageChart: document.querySelector("#taskUsageChart"),
  taskUsageNote: document.querySelector("#taskUsageNote"),
  taskForm: document.querySelector("#taskForm"),
  taskInput: document.querySelector("#taskInput"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  taskHint: document.querySelector("#taskHint"),
  composerState: document.querySelector("#composerState"),
  promptModal: document.querySelector("#promptModal"),
  promptEyebrow: document.querySelector("#promptEyebrow"),
  promptTitle: document.querySelector("#promptTitle"),
  promptMessage: document.querySelector("#promptMessage"),
  promptSymbol: document.querySelector("#promptSymbol"),
  rejectPrompt: document.querySelector("#rejectPrompt"),
  acceptPrompt: document.querySelector("#acceptPrompt"),
  stopPromptTask: document.querySelector("#stopPromptTask"),
  toast: document.querySelector("#toast"),
};

const appState = {
  snapshot: null,
  events: [],
  eventCursor: 0,
  trajectories: [],
  currentTaskId: null,
  currentPromptId: null,
  lastTaskStatus: "idle",
  viewingHistory: null,
  draftMode: true,
  toastTimer: null,
  preflightExitTimer: null,
  hasEnteredConsole: false,
  processExpanded: false,
};

const taskLabels = {
  idle: "空闲",
  running: "执行中",
  waiting_user: "等待你操作",
  cancelling: "正在停止",
  success: "已完成",
  failed: "未完成",
  cancelled: "已停止",
};
const phaseLabels = {
  idle: "等待任务",
  initializing: "正在初始化任务",
  observing: "正在观察手机屏幕",
  planning: "正在思考下一步操作",
  executing: "正在操作手机",
  verifying: "正在验证操作结果",
  recovering: "正在调整执行策略",
  waiting_user: "正在等待你的操作",
  cancelling: "正在停止当前任务",
  completed: "任务已经完成",
  failed: "任务执行未完成",
  cancelled: "任务已取消",
};
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

const busyTaskStatuses = new Set(["running", "waiting_user", "cancelling"]);
const SVG_NS = "http://www.w3.org/2000/svg";

function isTaskBusy(status) {
  return busyTaskStatuses.has(status);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setConnection(online) {
  elements.connection.dataset.connection = online ? "online" : "offline";
  elements.connectionLabel.textContent = online ? "本地服务已连接" : "连接已中断";
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  clearTimeout(appState.toastTimer);
  appState.toastTimer = setTimeout(() => elements.toast.classList.remove("visible"), 2600);
}

function formatClock(seconds) {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const rest = safe % 60;
  return hours > 0
    ? [hours, minutes, rest].map((part) => String(part).padStart(2, "0")).join(":")
    : [minutes, rest].map((part) => String(part).padStart(2, "0")).join(":");
}

function formatTime(timestamp) {
  if (!timestamp) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date(timestamp * 1000));
}

function formatDate(timestamp) {
  if (!timestamp) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(timestamp * 1000));
}

function truncate(text, length = 46) {
  const value = String(text || "").trim();
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function formatTokens(value) {
  return value === null ? "—" : new Intl.NumberFormat("zh-CN").format(Math.round(value));
}

function usageSamples(events, pricing) {
  let request = 0;
  return events.filter((event) => event.type === "model_response").map((event) => {
    request += 1;
    const metrics = event.payload?.metrics || {};
    const promptTokens = finiteNumber(metrics.prompt_tokens);
    const completionTokens = finiteNumber(metrics.completion_tokens);
    let totalTokens = finiteNumber(metrics.total_tokens);
    if (totalTokens === null && (promptTokens !== null || completionTokens !== null)) {
      totalTokens = (promptTokens || 0) + (completionTokens || 0);
    }
    const totalTime = finiteNumber(metrics.total_time);
    const hasBillableTokens = promptTokens !== null || completionTokens !== null;
    const cost = pricing?.configured && hasBillableTokens
      ? ((promptTokens || 0) * Number(pricing.input_per_million_tokens || 0)
        + (completionTokens || 0) * Number(pricing.output_per_million_tokens || 0)) / 1_000_000
      : null;
    return {
      request,
      step: Number.isInteger(event.step) ? event.step : event.payload?.step,
      promptTokens,
      completionTokens,
      totalTokens,
      totalTime,
      cost,
    };
  });
}

function svgNode(name, attributes = {}, content = null) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (content !== null) node.textContent = content;
  return node;
}

function metricPoints(samples, xFor, yFor, field) {
  return samples
    .map((sample, index) => ({ sample, index }))
    .filter(({ sample }) => sample[field] !== null)
    .map(({ sample, index }) => `${xFor(index)},${yFor(sample[field])}`)
    .join(" ");
}

function renderUsageChart(samples, target, pricing) {
  const width = 760;
  const hasCost = Boolean(pricing?.configured && samples.some((sample) => sample.cost !== null));
  const height = hasCost ? 320 : 250;
  const left = 55;
  const right = 705;
  const top = 34;
  const bottom = 188;
  const plotWidth = right - left;
  const plotHeight = bottom - top;
  const maxTokens = Math.max(1, ...samples.map((sample) => sample.totalTokens || 0));
  const maxTime = Math.max(1, ...samples.map((sample) => sample.totalTime || 0));
  const xFor = (index) => samples.length === 1
    ? left + plotWidth / 2
    : left + (index / (samples.length - 1)) * plotWidth;
  const tokenY = (value) => bottom - (value / maxTokens) * plotHeight;
  const timeY = (value) => bottom - (value / maxTime) * plotHeight;
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" });

  for (let index = 0; index <= 4; index += 1) {
    const ratio = index / 4;
    const y = top + ratio * plotHeight;
    svg.append(svgNode("line", { x1: left, y1: y, x2: right, y2: y, class: "usage-grid-line" }));
    svg.append(svgNode("text", { x: left - 8, y: y + 3, class: "usage-axis-label", "text-anchor": "end" }, formatTokens(maxTokens * (1 - ratio))));
    svg.append(svgNode("text", { x: right + 8, y: y + 3, class: "usage-axis-label", "text-anchor": "start" }, `${(maxTime * (1 - ratio)).toFixed(1)}s`));
  }

  svg.append(svgNode("text", { x: left, y: 16, class: "usage-series-label token" }, "总 Token"));
  svg.append(svgNode("text", { x: right, y: 16, class: "usage-series-label time", "text-anchor": "end" }, "模型耗时"));
  const tokenPoints = metricPoints(samples, xFor, tokenY, "totalTokens");
  const timePoints = metricPoints(samples, xFor, timeY, "totalTime");
  if (tokenPoints) svg.append(svgNode("polyline", { points: tokenPoints, class: "usage-line token" }));
  if (timePoints) svg.append(svgNode("polyline", { points: timePoints, class: "usage-line time" }));

  samples.forEach((sample, index) => {
    const x = xFor(index);
    if (sample.totalTokens !== null) {
      const point = svgNode("circle", { cx: x, cy: tokenY(sample.totalTokens), r: 4, class: "usage-point token" });
      point.append(svgNode("title", {}, `请求 ${sample.request}：${formatTokens(sample.totalTokens)} Token`));
      svg.append(point);
    }
    if (sample.totalTime !== null) {
      const point = svgNode("circle", { cx: x, cy: timeY(sample.totalTime), r: 4, class: "usage-point time" });
      point.append(svgNode("title", {}, `请求 ${sample.request}：${sample.totalTime.toFixed(2)} 秒`));
      svg.append(point);
    }
    svg.append(svgNode("text", { x, y: bottom + 22, class: "usage-x-label", "text-anchor": "middle" }, `#${sample.request}`));
  });

  if (hasCost) {
    const costTop = 245;
    const costBottom = 292;
    const maxCost = Math.max(0.000001, ...samples.map((sample) => sample.cost || 0));
    const costY = (value) => costBottom - (value / maxCost) * (costBottom - costTop);
    svg.append(svgNode("line", { x1: left, y1: costBottom, x2: right, y2: costBottom, class: "usage-grid-line" }));
    svg.append(svgNode("text", { x: left, y: costTop - 10, class: "usage-series-label cost" }, `单次费用 · ${pricing.currency}`));
    const costPoints = metricPoints(samples, xFor, costY, "cost");
    if (costPoints) svg.append(svgNode("polyline", { points: costPoints, class: "usage-line cost" }));
    samples.forEach((sample, index) => {
      if (sample.cost === null) return;
      const point = svgNode("circle", { cx: xFor(index), cy: costY(sample.cost), r: 3.5, class: "usage-point cost" });
      point.append(svgNode("title", {}, `请求 ${sample.request}：${pricing.currency} ${sample.cost.toFixed(6)}`));
      svg.append(point);
    });
  }

  const breakdown = document.createElement("div");
  breakdown.className = "usage-breakdown";
  samples.forEach((sample) => {
    const item = document.createElement("span");
    const costText = sample.cost === null ? "" : ` · ${pricing.currency} ${sample.cost.toFixed(6)}`;
    item.textContent = `#${sample.request}  ${formatTokens(sample.totalTokens)} tok · ${sample.totalTime === null ? "—" : `${sample.totalTime.toFixed(1)}s`}${costText}`;
    breakdown.append(item);
  });
  target.replaceChildren(svg, breakdown);
}

function renderUsagePanel(events, status, panel, summary, chart, note) {
  const finished = ["success", "failed", "cancelled"].includes(status);
  const pricing = appState.snapshot?.pricing || {};
  const samples = usageSamples(events, pricing);
  panel.hidden = !finished || !samples.length;
  if (panel.hidden) return;

  const sum = (field) => samples.reduce((total, sample) => total + (sample[field] || 0), 0);
  const promptTokens = sum("promptTokens");
  const completionTokens = sum("completionTokens");
  const totalTokens = sum("totalTokens");
  const totalTime = sum("totalTime");
  const hasPromptTokens = samples.some((sample) => sample.promptTokens !== null);
  const hasCompletionTokens = samples.some((sample) => sample.completionTokens !== null);
  const hasTotalTokens = samples.some((sample) => sample.totalTokens !== null);
  const hasTotalTime = samples.some((sample) => sample.totalTime !== null);
  const totalCost = samples.some((sample) => sample.cost !== null) ? sum("cost") : null;
  const missingUsage = samples.some((sample) => (
    sample.promptTokens === null || sample.completionTokens === null
  ));
  const cards = [
    ["模型请求", `${samples.length} 次`],
    ["输入 Token", formatTokens(hasPromptTokens ? promptTokens : null)],
    ["输出 Token", formatTokens(hasCompletionTokens ? completionTokens : null)],
    ["总 Token", formatTokens(hasTotalTokens ? totalTokens : null)],
    ["模型耗时", hasTotalTime ? `${totalTime.toFixed(1)} 秒` : "—"],
    ["估算费用", totalCost === null
      ? (pricing.configured ? "不可用" : "未配置")
      : `${pricing.currency} ${totalCost.toFixed(6)}`],
  ];
  summary.replaceChildren();
  cards.forEach(([label, value]) => {
    const item = document.createElement("span");
    const small = document.createElement("small");
    const strong = document.createElement("b");
    small.textContent = label;
    strong.textContent = value;
    item.append(small, strong);
    summary.append(item);
  });
  renderUsageChart(samples, chart, pricing);
  note.textContent = pricing.configured
    ? `费用按当前配置估算：输入 ${pricing.currency} ${pricing.input_per_million_tokens}/百万 Token，输出 ${pricing.currency} ${pricing.output_per_million_tokens}/百万 Token。${missingUsage ? " 部分请求未返回用量，汇总可能不完整。" : ""}`
    : "尚未配置 Token 单价；设置 INPUT_PRICE_PER_1M_TOKENS 和 OUTPUT_PRICE_PER_1M_TOKENS 后即可显示费用曲线。";
}

function renderChecks(startup) {
  elements.startupMessage.textContent = startup.message || "等待启动检查";
  elements.recheckButton.disabled = startup.status === "checking";
  const existing = new Map(
    [...elements.checkList.querySelectorAll(".check-card")].map((node) => [node.dataset.id, node]),
  );
  (startup.checks || []).forEach((check) => {
    let card = existing.get(check.id);
    if (!card) {
      card = document.createElement("details");
      card.className = "check-card";
      card.dataset.id = check.id;
      const summary = document.createElement("summary");
      const head = document.createElement("div");
      head.className = "check-card-head";
      const state = document.createElement("span");
      state.className = "check-state";
      const label = document.createElement("b");
      head.append(state, label);
      const description = document.createElement("p");
      summary.append(head, description);
      const details = document.createElement("pre");
      card.append(summary, details);
      elements.checkList.append(card);
    }
    card.dataset.status = check.status;
    card.querySelector(".check-state").textContent = {
      passed: "✓", warning: "!", failed: "×", skipped: "–", running: "",
    }[check.status] || "·";
    card.querySelector("b").textContent = check.label;
    card.querySelector("p").textContent = check.summary || "等待检查";
    card.querySelector("pre").textContent = check.details || "暂无详细输出";
    card.querySelector("pre").hidden = !check.details;
  });

  const ready = startup.status === "ready";
  const checks = startup.checks || [];
  const completed = checks.filter((check) => !["pending", "running"].includes(check.status)).length;
  const progress = checks.length ? Math.round((completed / checks.length) * 100) : 0;
  elements.deviceIdentity.textContent = startup.device_id || "等待设备";
  elements.modelIdentity.textContent = startup.model_name || "等待配置";
  elements.endpointIdentity.textContent = startup.base_url || "等待配置";
  elements.preflightGate.dataset.status = startup.status || "idle";
  elements.preflightCount.textContent = ready
    ? `${checks.length} 项检查已完成`
    : (startup.status === "failed" ? `${completed} / ${checks.length} 项已完成` : `正在检查 ${completed} / ${checks.length}`);
  elements.preflightProgress.style.width = `${ready ? 100 : progress}%`;
  elements.startupTitle.textContent = {
    idle: "正在准备运行环境", checking: "正在准备运行环境", ready: "运行环境已就绪", failed: "环境检查未通过",
  }[startup.status] || "正在准备运行环境";
  elements.preflightState.querySelector("b").textContent = {
    idle: "准备中", checking: "检查中", ready: "已通过", failed: "未通过",
  }[startup.status] || "准备中";
  elements.preflightHelp.textContent = startup.status === "failed"
    ? "请根据失败项的详细信息修复环境，然后重新检查。"
    : (ready ? "运行环境已就绪，正在进入控制台…" : "检查通常只需片刻，通过后将自动进入控制台。");
  elements.recheckButton.hidden = startup.status !== "failed";
  elements.reuseNote.dataset.ready = String(ready);
  elements.reuseLabel.textContent = ready
    ? (startup.reused ? "本次会话正在复用检查结果" : "检查结果可在本次会话复用")
    : "检查结果尚未建立";

  if (ready && !appState.hasEnteredConsole && !appState.preflightExitTimer) {
    appState.preflightExitTimer = setTimeout(enterConsole, 650);
  }
}

function enterConsole() {
  if (appState.hasEnteredConsole) return;
  appState.hasEnteredConsole = true;
  appState.preflightExitTimer = null;
  elements.preflightGate.classList.add("is-leaving");
  document.body.classList.remove("preflight-active");
  elements.appSurface.removeAttribute("inert");
  elements.appSurface.setAttribute("aria-hidden", "false");
  setTimeout(() => {
    elements.preflightGate.hidden = true;
    elements.taskInput.focus({ preventScroll: true });
  }, 360);
}

function renderRuntime(snapshot) {
  const { startup, task } = snapshot;
  const ready = startup.status === "ready";
  const busy = isTaskBusy(task.status);
  const runtimeIdentity = ready
    ? ` · ${startup.device_id || "device"} · ${startup.model_name || "model"}`
    : "";
  elements.composerState.dataset.ready = String(ready && !busy);
  elements.composerState.textContent = !ready
    ? "Agent 尚未就绪"
    : `${busy ? "Agent 正在执行" : "Agent 已就绪"}${runtimeIdentity}`;
  elements.taskInput.disabled = !ready || busy;
  elements.runButton.disabled = !ready || busy || !elements.taskInput.value.trim();
  elements.runButton.hidden = busy;
  elements.stopButton.hidden = !busy;
  elements.stopButton.disabled = task.status === "cancelling";
  elements.taskHint.textContent = !ready
    ? "启动检查通过后即可提交任务"
    : (busy ? "当前任务结束后可以继续提交" : "Enter 发送，Shift + Enter 换行");
}

function renderTask(task) {
  if (appState.viewingHistory) return;
  const status = task.status || "idle";
  const busy = isTaskBusy(status);
  if ((!task.goal || appState.draftMode) && !busy) {
    showWelcome();
    elements.taskStatus.dataset.status = "idle";
    elements.taskStatus.querySelector("span").textContent = "空闲";
    return;
  }

  appState.draftMode = false;
  elements.welcomeState.hidden = true;
  elements.historyDetail.hidden = true;
  elements.threadView.hidden = false;
  elements.currentGoal.textContent = task.goal || elements.currentGoal.textContent;
  elements.conversationTitle.textContent = truncate(task.goal || "当前任务", 34);
  elements.taskStatus.dataset.status = status;
  elements.taskStatus.querySelector("span").textContent = taskLabels[status] || status;
  const effectivePhase = ["waiting_user", "cancelling"].includes(status)
    ? status
    : (task.phase || status);
  elements.workProcess.dataset.active = String(busy);
  elements.workProcess.dataset.status = status;
  elements.processTitle.textContent = busy
    ? (phaseLabels[effectivePhase] || "PhoneAgent 正在工作")
    : (status === "success" ? "工作过程已完成" : "工作过程已结束");

  const resultText = task.error || task.result || "";
  elements.taskResultPanel.hidden = !resultText || busy;
  elements.taskResultPanel.dataset.status = status;
  elements.taskResultPanel.querySelector(":scope > span").textContent = status === "success"
    ? "✓"
    : (status === "cancelled" ? "■" : "!");
  elements.taskResult.textContent = resultText;
  renderEvents();
}

function showWelcome() {
  if (appState.viewingHistory) return;
  elements.welcomeState.hidden = false;
  elements.threadView.hidden = true;
  elements.historyDetail.hidden = true;
  elements.conversationTitle.textContent = "新任务";
}

function eventKind(type) {
  if (["model_request", "model_response"].includes(type)) return "model";
  if (["action", "execution"].includes(type)) return "action";
  if (type === "verification") return "verification";
  if (["recovery", "user_prompt", "user_response"].includes(type)) return "recovery";
  if (["error", "web_task_error"].includes(type)) return "error";
  if (["finish", "web_task_finished"].includes(type)) return "finish";
  return "system";
}

function eventGlyph(type) {
  return {
    model: "✦", action: "↗", verification: "✓", recovery: "↺", error: "!", finish: "✓", system: "·",
  }[eventKind(type)];
}

function summarizeEvent(event) {
  const payload = event.payload || {};
  if (event.type === "phase_change") return event.message || payload.reason || "状态已更新";
  if (event.type === "observation") {
    return [payload.current_app, payload.screen_width && `${payload.screen_width}×${payload.screen_height}`]
      .filter(Boolean).join(" · ") || event.message;
  }
  if (event.type === "model_request") return "正在根据当前屏幕决定下一步操作";
  if (event.type === "model_response") {
    return truncate(payload.thinking || payload.raw_content || event.message, 220);
  }
  if (event.type === "action") return payload.action ? JSON.stringify(payload.action) : event.message;
  if (event.type === "execution") return event.message || (payload.command_success ? "操作命令执行成功" : "操作命令执行失败");
  if (event.type === "verification") return event.message || `${payload.status || ""} · ${payload.policy || ""}`;
  if (event.type === "recovery") return event.message || payload.strategy || payload.decision?.strategy;
  return event.message || "执行记录已更新";
}

function timelineEvents(events) {
  const hiddenTypes = new Set(["metrics", "web_task_started", "web_task_finished"]);
  return events.filter((event) => !hiddenTypes.has(event.type));
}

function processEvents(events) {
  const usefulTypes = new Set([
    "model_response", "action", "execution", "verification", "recovery",
    "user_prompt", "user_response", "error", "note", "finish", "web_task_error",
    "web_task_cancel_requested",
  ]);
  return events.filter((event) => usefulTypes.has(event.type));
}

function latestProcessText(events, task) {
  const latestModelResponse = [...events].reverse().find((event) => event.type === "model_response");
  const modelContent = latestModelResponse
    ? String(
      latestModelResponse.payload?.thinking
      || latestModelResponse.payload?.raw_content
      || latestModelResponse.message
      || "",
    ).trim()
    : "";
  if (modelContent) return truncate(modelContent, 260);
  const latest = processEvents(events).at(-1);
  if (latest) return truncate(summarizeEvent(latest), 260);
  return phaseLabels[task?.phase] || "正在等待模型返回第一步计划…";
}

function renderProcessNotice(events) {
  const latestModelResponse = [...events].reverse().find((event) => event.type === "model_response");
  const protocolError = String(latestModelResponse?.payload?.protocol_error || "").trim();
  elements.processNotice.hidden = !protocolError;
  elements.processNotice.textContent = protocolError ? `输出格式错误 · ${protocolError}` : "";
}

function renderTimeline(events, target, { live = false, waitingText = null } = {}) {
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
    const head = document.createElement("header");
    const title = document.createElement("b");
    title.textContent = eventLabels[event.type] || event.type;
    const meta = document.createElement("span");
    const step = Number.isInteger(event.step) ? event.step : event.payload?.step;
    meta.textContent = `${Number.isInteger(step) ? `第 ${step} 步 · ` : ""}${formatTime(event.timestamp)}`;
    head.append(title, meta);
    const summary = document.createElement("p");
    summary.textContent = summarizeEvent(event);
    body.append(head, summary);
    if (event.payload && Object.keys(event.payload).length) {
      const details = document.createElement("details");
      const label = document.createElement("summary");
      label.textContent = "查看详细信息";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(event.payload, null, 2);
      details.append(label, pre);
      body.append(details);
    }
    item.append(marker, body);
    target.append(item);
  });

  if (live) {
    const waiting = document.createElement("div");
    waiting.className = "timeline-waiting";
    const spinner = document.createElement("i");
    const text = document.createElement("span");
    text.textContent = waitingText || phaseLabels[appState.snapshot?.task?.phase] || "等待下一步执行…";
    waiting.append(spinner, text);
    target.append(waiting);
  } else if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "没有可显示的执行记录";
    target.append(empty);
  }
}

function renderEvents() {
  if (appState.viewingHistory || elements.threadView.hidden) return;
  const task = appState.snapshot?.task;
  const taskId = task?.id;
  const events = appState.events.filter((event) => taskId && event.task_id === taskId);
  const usefulEvents = processEvents(events);
  elements.eventCount.textContent = `${usefulEvents.length} 条`;
  elements.processLatest.textContent = latestProcessText(events, task);
  renderProcessNotice(events);
  renderUsagePanel(
    events,
    task?.status,
    elements.taskUsagePanel,
    elements.taskUsageSummary,
    elements.taskUsageChart,
    elements.taskUsageNote,
  );
  const nearBottom = elements.conversationScroll.scrollHeight
    - elements.conversationScroll.scrollTop
    - elements.conversationScroll.clientHeight < 180;
  if (!appState.processExpanded) return;
  renderTimeline(usefulEvents, elements.eventFeed, {
    live: isTaskBusy(task?.status),
  });
  if (nearBottom) requestAnimationFrame(() => {
    elements.conversationScroll.scrollTop = elements.conversationScroll.scrollHeight;
  });
}

function renderPrompt(prompt) {
  if (!prompt) {
    appState.currentPromptId = null;
    elements.promptModal.hidden = true;
    return;
  }
  appState.currentPromptId = prompt.id;
  const takeover = prompt.type === "takeover";
  elements.promptEyebrow.textContent = takeover ? "MANUAL TAKEOVER" : "SENSITIVE ACTION";
  elements.promptTitle.textContent = takeover ? "请在手机上完成操作" : "需要你的确认";
  elements.promptSymbol.textContent = takeover ? "↺" : "!";
  elements.promptMessage.textContent = prompt.message;
  elements.rejectPrompt.hidden = takeover;
  elements.acceptPrompt.querySelector("span").textContent = takeover ? "我已完成，继续" : "确认并继续";
  elements.rejectPrompt.disabled = false;
  elements.acceptPrompt.disabled = false;
  elements.stopPromptTask.disabled = false;
  elements.promptModal.hidden = false;
}

async function fetchState() {
  try {
    const snapshot = await api("/api/state");
    setConnection(true);
    appState.snapshot = snapshot;
    if (snapshot.task.id && snapshot.task.id !== appState.currentTaskId) {
      appState.currentTaskId = snapshot.task.id;
      appState.draftMode = false;
      appState.viewingHistory = null;
      setProcessExpanded(false);
    }
    if (
      isTaskBusy(appState.lastTaskStatus)
      && ["success", "failed", "cancelled"].includes(snapshot.task.status)
    ) {
      setProcessExpanded(false);
    }
    renderChecks(snapshot.startup);
    renderRuntime(snapshot);
    renderTask(snapshot.task);
    renderPrompt(snapshot.task.status === "cancelling" ? null : snapshot.pending_prompt);
    renderTrajectoryList();
    elements.sessionClock.textContent = formatClock(Date.now() / 1000 - snapshot.session.started_at);
    if (appState.lastTaskStatus !== snapshot.task.status) {
      if (["success", "failed", "cancelled"].includes(snapshot.task.status)) loadTrajectories();
      appState.lastTaskStatus = snapshot.task.status;
    }
  } catch (error) {
    setConnection(false);
  } finally {
    setTimeout(fetchState, 800);
  }
}

async function fetchEvents() {
  try {
    const payload = await api(`/api/events?after=${appState.eventCursor}`);
    if (payload.events?.length) {
      appState.events.push(...payload.events);
      appState.events = appState.events.slice(-2000);
      renderEvents();
    }
    appState.eventCursor = Math.max(appState.eventCursor, payload.cursor || 0);
  } catch (error) {
    // State polling owns the connection indicator.
  } finally {
    setTimeout(fetchEvents, 550);
  }
}

function showOptimisticTask(task) {
  appState.draftMode = false;
  appState.viewingHistory = null;
  elements.welcomeState.hidden = true;
  elements.historyDetail.hidden = true;
  elements.threadView.hidden = false;
  elements.currentGoal.textContent = task;
  elements.conversationTitle.textContent = truncate(task, 34);
  elements.taskStatus.dataset.status = "running";
  elements.taskStatus.querySelector("span").textContent = "提交中";
  elements.runButton.hidden = true;
  elements.stopButton.hidden = false;
  elements.stopButton.disabled = true;
  setProcessExpanded(false);
  elements.workProcess.dataset.active = "true";
  elements.workProcess.dataset.status = "running";
  elements.processTitle.textContent = "正在提交任务";
  elements.processLatest.textContent = "即将开始观察手机屏幕";
  elements.processNotice.hidden = true;
  elements.processNotice.textContent = "";
  elements.eventCount.textContent = "0 条";
  elements.taskUsagePanel.hidden = true;
}

async function submitTask(event) {
  event.preventDefault();
  const task = elements.taskInput.value.trim();
  if (!task) return;
  elements.runButton.disabled = true;
  showOptimisticTask(task);
  closeSidebar();
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({ task }) });
    elements.stopButton.disabled = false;
    elements.taskInput.value = "";
    resizeTaskInput();
    showToast("任务已提交");
  } catch (error) {
    elements.stopButton.hidden = true;
    elements.runButton.hidden = false;
    showToast(error.message);
    if (!appState.snapshot?.task?.goal) {
      appState.draftMode = true;
      showWelcome();
    }
  }
}

async function cancelTask() {
  if (elements.stopButton.hidden) return;
  elements.stopButton.disabled = true;
  elements.stopPromptTask.disabled = true;
  elements.taskStatus.dataset.status = "cancelling";
  elements.taskStatus.querySelector("span").textContent = "正在停止";
  elements.processTitle.textContent = "正在停止当前任务";
  try {
    await api("/api/tasks/cancel", { method: "POST", body: JSON.stringify({}) });
    elements.promptModal.hidden = true;
    showToast("已请求停止任务");
  } catch (error) {
    elements.stopButton.disabled = false;
    elements.stopPromptTask.disabled = false;
    showToast(error.message);
  }
}

async function rerunChecks() {
  elements.recheckButton.disabled = true;
  try {
    await api("/api/checks", { method: "POST", body: JSON.stringify({}) });
    showToast("正在重新进行启动检查");
  } catch (error) {
    showToast(error.message);
  }
}

async function respondToPrompt(accepted) {
  if (!appState.currentPromptId) return;
  elements.rejectPrompt.disabled = true;
  elements.acceptPrompt.disabled = true;
  try {
    await api("/api/prompts/respond", {
      method: "POST",
      body: JSON.stringify({ id: appState.currentPromptId, accepted }),
    });
    elements.promptModal.hidden = true;
  } catch (error) {
    showToast(error.message);
  }
}

async function loadTrajectories() {
  try {
    const payload = await api("/api/trajectories");
    appState.trajectories = payload.trajectories || [];
    renderTrajectoryList();
  } catch (error) {
    elements.trajectoryList.textContent = `读取历史任务失败：${error.message}`;
  }
}

function historyButton({ title, meta, success, active, current = false, onClick }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "history-item";
  button.classList.toggle("active", active);
  button.dataset.success = success === true ? "true" : success === false ? "false" : "unknown";
  const icon = document.createElement("span");
  icon.className = current ? "history-current-icon" : "history-status-icon";
  icon.textContent = current ? "↗" : "";
  const copy = document.createElement("span");
  const label = document.createElement("b");
  label.textContent = title;
  const detail = document.createElement("small");
  detail.textContent = meta;
  copy.append(label, detail);
  button.append(icon, copy);
  button.addEventListener("click", onClick);
  return button;
}

function renderTrajectoryList() {
  const query = elements.trajectorySearch.value.trim().toLocaleLowerCase();
  elements.trajectoryList.replaceChildren();
  const current = appState.snapshot?.task;
  if (current?.goal && `${current.goal} ${current.id || ""}`.toLocaleLowerCase().includes(query)) {
    elements.trajectoryList.append(historyButton({
      title: current.goal,
      meta: isTaskBusy(current.status) ? "正在执行" : "当前任务",
      success: current.status === "success" ? true : (["failed", "cancelled"].includes(current.status) ? false : null),
      active: !appState.viewingHistory && !appState.draftMode,
      current: true,
      onClick: showCurrentTask,
    }));
  }
  const items = appState.trajectories.filter((item) => {
    const haystack = `${item.task || ""} ${item.run_id || ""} ${item.filename || ""}`.toLocaleLowerCase();
    return !query || haystack.includes(query);
  });
  if (current?.goal && items.length) {
    const divider = document.createElement("p");
    divider.className = "history-section-label";
    divider.textContent = "最近";
    elements.trajectoryList.append(divider);
  }
  items.forEach((item) => {
    elements.trajectoryList.append(historyButton({
      title: item.task || item.filename,
      meta: `${formatDate(item.started_at)} · ${item.event_count || 0} 条记录`,
      success: item.success,
      active: appState.viewingHistory === item.filename,
      onClick: () => openTrajectory(item.filename),
    }));
  });
  if (!elements.trajectoryList.children.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = query ? "没有匹配的历史任务" : "还没有历史任务";
    elements.trajectoryList.append(empty);
  }
}

async function openTrajectory(filename) {
  try {
    const trajectory = await api(`/api/trajectory?name=${encodeURIComponent(filename)}`);
    appState.viewingHistory = filename;
    appState.draftMode = false;
    elements.welcomeState.hidden = true;
    elements.threadView.hidden = true;
    elements.historyDetail.hidden = false;
    elements.conversationTitle.textContent = truncate(trajectory.task || "历史任务", 34);
    elements.taskStatus.dataset.status = trajectory.success ? "success" : "failed";
    elements.taskStatus.querySelector("span").textContent = trajectory.success ? "已完成" : "未完成";
    elements.trajectoryResult.dataset.success = String(trajectory.success);
    elements.trajectoryResult.textContent = trajectory.success ? "已完成" : "未完成";
    elements.trajectoryTask.textContent = trajectory.task || "未命名任务";
    elements.downloadTrajectory.href = `/api/trajectory?name=${encodeURIComponent(filename)}&download=1`;
    elements.trajectoryMeta.replaceChildren();
    [
      formatDate(trajectory.started_at),
      `${Number(trajectory.duration_seconds || 0).toFixed(1)} 秒`,
      `${trajectory.event_count || 0} 条记录`,
    ].forEach((text) => {
      const chip = document.createElement("span");
      chip.textContent = text;
      elements.trajectoryMeta.append(chip);
    });
    renderTimeline(trajectory.events || [], elements.trajectoryEvents);
    renderUsagePanel(
      trajectory.events || [],
      trajectory.success ? "success" : "failed",
      elements.trajectoryUsagePanel,
      elements.trajectoryUsageSummary,
      elements.trajectoryUsageChart,
      elements.trajectoryUsageNote,
    );
    renderTrajectoryList();
    closeSidebar();
    elements.conversationScroll.scrollTop = 0;
  } catch (error) {
    showToast(error.message);
  }
}

function showCurrentTask() {
  appState.viewingHistory = null;
  appState.draftMode = false;
  renderTask(appState.snapshot?.task || {});
  renderTrajectoryList();
  closeSidebar();
  elements.conversationScroll.scrollTop = elements.conversationScroll.scrollHeight;
}

function setProcessExpanded(expanded) {
  appState.processExpanded = Boolean(expanded);
  elements.workProcessToggle.setAttribute("aria-expanded", String(appState.processExpanded));
  elements.workProcessDetails.hidden = !appState.processExpanded;
  if (appState.processExpanded) renderEvents();
}

function toggleProcess() {
  setProcessExpanded(!appState.processExpanded);
}

function startNewTask() {
  const busy = isTaskBusy(appState.snapshot?.task?.status);
  if (busy) {
    showToast("请等待当前任务结束后再新建任务");
    return;
  }
  appState.viewingHistory = null;
  appState.draftMode = true;
  setProcessExpanded(false);
  elements.taskUsagePanel.hidden = true;
  showWelcome();
  elements.taskStatus.dataset.status = "idle";
  elements.taskStatus.querySelector("span").textContent = "空闲";
  renderTrajectoryList();
  closeSidebar();
  elements.taskInput.value = "";
  resizeTaskInput();
  elements.taskInput.focus();
}

function openSidebar() {
  if (window.matchMedia("(min-width: 901px)").matches) {
    setSidebarCollapsed(false);
  } else {
    document.body.classList.add("sidebar-open");
  }
}

function closeSidebar() {
  document.body.classList.remove("sidebar-open");
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  elements.sidebarCollapse.setAttribute("aria-expanded", String(!collapsed));
  elements.sidebarCollapse.setAttribute("aria-label", collapsed ? "展开任务历史" : "收起任务历史");
  try {
    localStorage.setItem("phoneagent-sidebar-collapsed", collapsed ? "1" : "0");
  } catch (error) {
    // Local storage is optional; the current page still keeps the chosen state.
  }
}

function toggleSidebar() {
  if (window.matchMedia("(max-width: 900px)").matches) {
    closeSidebar();
    return;
  }
  setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
}

function restoreSidebarState() {
  if (!window.matchMedia("(min-width: 901px)").matches) return;
  try {
    setSidebarCollapsed(localStorage.getItem("phoneagent-sidebar-collapsed") === "1");
  } catch (error) {
    setSidebarCollapsed(false);
  }
}

function resizeTaskInput() {
  elements.taskInput.style.height = "auto";
  elements.taskInput.style.height = `${Math.min(elements.taskInput.scrollHeight, 180)}px`;
  const task = appState.snapshot?.task;
  const ready = appState.snapshot?.startup?.status === "ready";
  const busy = task && isTaskBusy(task.status);
  elements.runButton.disabled = !ready || busy || !elements.taskInput.value.trim();
}

elements.taskForm.addEventListener("submit", submitTask);
elements.stopButton.addEventListener("click", cancelTask);
elements.stopPromptTask.addEventListener("click", cancelTask);
elements.workProcessToggle.addEventListener("click", toggleProcess);
elements.taskInput.addEventListener("input", resizeTaskInput);
elements.taskInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!elements.runButton.disabled) elements.taskForm.requestSubmit();
  }
});
document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.taskInput.value = button.dataset.example;
    resizeTaskInput();
    elements.taskInput.focus();
  });
});
elements.recheckButton.addEventListener("click", rerunChecks);
elements.rejectPrompt.addEventListener("click", () => respondToPrompt(false));
elements.acceptPrompt.addEventListener("click", () => respondToPrompt(true));
elements.refreshTrajectories.addEventListener("click", loadTrajectories);
elements.trajectorySearch.addEventListener("input", renderTrajectoryList);
elements.closeTrajectory.addEventListener("click", showCurrentTask);
elements.newTaskButton.addEventListener("click", startNewTask);
elements.mobileSidebarButton.addEventListener("click", openSidebar);
elements.sidebarCollapse.addEventListener("click", toggleSidebar);
elements.sidebarClose.addEventListener("click", closeSidebar);
elements.sidebarScrim.addEventListener("click", closeSidebar);

restoreSidebarState();
fetchState();
fetchEvents();
loadTrajectories();
