"use strict";

const elements = {
  connection: document.querySelector(".connection-pill"),
  connectionLabel: document.querySelector("#connectionLabel"),
  sessionClock: document.querySelector("#sessionClock"),
  startupMessage: document.querySelector("#startupMessage"),
  checkList: document.querySelector("#checkList"),
  recheckButton: document.querySelector("#recheckButton"),
  deviceIdentity: document.querySelector("#deviceIdentity"),
  modelIdentity: document.querySelector("#modelIdentity"),
  endpointIdentity: document.querySelector("#endpointIdentity"),
  reuseLabel: document.querySelector("#reuseLabel"),
  reuseNote: document.querySelector(".reuse-note"),
  taskForm: document.querySelector("#taskForm"),
  taskInput: document.querySelector("#taskInput"),
  runButton: document.querySelector("#runButton"),
  taskHint: document.querySelector("#taskHint"),
  composerState: document.querySelector("#composerState"),
  taskStatus: document.querySelector("#taskStatus"),
  currentGoal: document.querySelector("#currentGoal"),
  taskResult: document.querySelector("#taskResult"),
  phaseMetric: document.querySelector("#phaseMetric"),
  stepMetric: document.querySelector("#stepMetric"),
  appMetric: document.querySelector("#appMetric"),
  recoveryMetric: document.querySelector("#recoveryMetric"),
  thinkingOutput: document.querySelector("#thinkingOutput"),
  actionOutput: document.querySelector("#actionOutput"),
  proofOutput: document.querySelector("#proofOutput"),
  verificationMessage: document.querySelector("#verificationMessage"),
  phaseRail: document.querySelector("#phaseRail"),
  eventFeed: document.querySelector("#eventFeed"),
  eventCount: document.querySelector("#eventCount"),
  runtimeState: document.querySelector("#runtimeState"),
  runtimeDetail: document.querySelector("#runtimeDetail"),
  deviceOrbit: document.querySelector(".device-orbit"),
  trajectoryDirectory: document.querySelector("#trajectoryDirectory"),
  deviceFact: document.querySelector("#deviceFact"),
  modelFact: document.querySelector("#modelFact"),
  trajectoryList: document.querySelector("#trajectoryList"),
  trajectorySearch: document.querySelector("#trajectorySearch"),
  refreshTrajectories: document.querySelector("#refreshTrajectories"),
  trajectoryDetail: document.querySelector("#trajectoryDetail"),
  closeTrajectory: document.querySelector("#closeTrajectory"),
  trajectoryResult: document.querySelector("#trajectoryResult"),
  trajectoryTask: document.querySelector("#trajectoryTask"),
  trajectoryMeta: document.querySelector("#trajectoryMeta"),
  trajectoryEvents: document.querySelector("#trajectoryEvents"),
  downloadTrajectory: document.querySelector("#downloadTrajectory"),
  promptModal: document.querySelector("#promptModal"),
  promptEyebrow: document.querySelector("#promptEyebrow"),
  promptTitle: document.querySelector("#promptTitle"),
  promptMessage: document.querySelector("#promptMessage"),
  promptSymbol: document.querySelector("#promptSymbol"),
  rejectPrompt: document.querySelector("#rejectPrompt"),
  acceptPrompt: document.querySelector("#acceptPrompt"),
  toast: document.querySelector("#toast"),
};

const appState = {
  snapshot: null,
  events: [],
  eventCursor: 0,
  eventFilter: "all",
  trajectories: [],
  currentTaskId: null,
  currentPromptId: null,
  lastTaskStatus: "idle",
  toastTimer: null,
};

const phaseOrder = ["observing", "planning", "executing", "verifying", "recovering"];
const taskLabels = {
  idle: "空闲",
  running: "运行中",
  waiting_user: "等待用户",
  success: "已完成",
  failed: "失败",
};
const eventLabels = {
  start: "任务开始",
  phase_change: "状态迁移",
  app_catalog: "应用目录",
  observation: "设备观察",
  model_request: "模型请求",
  model_response: "模型响应",
  thinking: "模型思考",
  action: "结构化动作",
  execution: "命令执行",
  verification: "结果验证",
  recovery: "恢复决策",
  finish: "运行结束",
  error: "运行错误",
  metrics: "模型指标",
  note: "运行笔记",
  startup: "启动检查",
  startup_ready: "运行时就绪",
  startup_failed: "启动失败",
  web_task_started: "任务已提交",
  web_task_finished: "任务已结束",
  web_task_error: "任务异常",
  user_prompt: "等待用户",
  user_response: "用户响应",
};

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
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(timestamp * 1000));
}

function formatDate(timestamp) {
  if (!timestamp) return "未知时间";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(timestamp * 1000));
}

function compactPath(path) {
  if (!path) return "runs";
  const parts = path.split("/").filter(Boolean);
  return parts.length > 3 ? `…/${parts.slice(-3).join("/")}` : path;
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
  elements.deviceIdentity.textContent = startup.device_id || "等待设备";
  elements.modelIdentity.textContent = startup.model_name || "等待配置";
  elements.endpointIdentity.textContent = startup.base_url || "等待配置";
  elements.deviceFact.textContent = startup.device_id || "—";
  elements.modelFact.textContent = startup.model_name || "—";
  const ready = startup.status === "ready";
  elements.reuseNote.dataset.ready = String(ready);
  elements.reuseLabel.textContent = ready
    ? (startup.reused ? "本次会话正在复用检查结果" : "检查结果可在本次会话复用")
    : "检查结果尚未建立";
}

function renderRuntime(snapshot) {
  const { startup, task } = snapshot;
  const ready = startup.status === "ready";
  const busy = ["running", "waiting_user"].includes(task.status);
  elements.composerState.dataset.ready = String(ready && !busy);
  elements.composerState.textContent = !ready
    ? (startup.status === "checking" ? "正在完成启动检查" : "运行时尚未就绪")
    : (busy ? "当前任务正在执行" : "可以提交任务");
  elements.taskInput.disabled = !ready || busy;
  elements.runButton.disabled = !ready || busy || !elements.taskInput.value.trim();
  elements.taskHint.textContent = !ready
    ? "启动检查通过后即可提交任务"
    : (busy ? "请等待当前任务完成" : "每次只运行一个任务，运行时会持续复用");

  elements.runtimeState.textContent = {
    idle: "等待启动检查",
    checking: "正在检查设备与模型",
    ready: busy ? "Agent 正在执行任务" : "已就绪，可以接收任务",
    failed: "启动检查未通过",
  }[startup.status] || startup.status;
  elements.runtimeDetail.textContent = startup.status === "ready"
    ? `${startup.device_id || "device"} · ${startup.model_name || "model"}`
    : startup.message;
  elements.deviceOrbit.dataset.ready = String(ready);
  elements.trajectoryDirectory.textContent = compactPath(snapshot.trajectory_dir);
  elements.trajectoryDirectory.title = snapshot.trajectory_dir;
}

function renderTask(task) {
  const status = task.status || "idle";
  elements.taskStatus.dataset.status = status;
  elements.taskStatus.querySelector("b").textContent = taskLabels[status] || status;
  elements.currentGoal.textContent = task.goal || "尚未提交任务";
  elements.taskResult.textContent = task.error || task.result || "";
  elements.taskResult.dataset.error = String(Boolean(task.error) || status === "failed");
  elements.phaseMetric.textContent = task.phase || "idle";
  elements.stepMetric.textContent = String(task.current_step || 0);
  elements.appMetric.textContent = task.current_app || "—";
  elements.recoveryMetric.textContent = String(task.recoveries || 0);
  elements.thinkingOutput.textContent = task.last_thinking || "等待模型响应";
  elements.actionOutput.textContent = task.last_action
    ? JSON.stringify(task.last_action, null, 2)
    : "等待动作";
  renderVerification(task.last_verification);
  renderPhaseRail(task.phase, status);
}

function renderPhaseRail(phase, status) {
  const currentIndex = phaseOrder.indexOf(phase);
  elements.phaseRail.querySelectorAll("[data-phase]").forEach((node, index) => {
    node.classList.toggle("active", phaseOrder[index] === phase && status !== "success");
    node.classList.toggle("complete", status === "success" || (currentIndex >= 0 && index < currentIndex));
  });
}

function renderVerification(verification) {
  const values = {
    command: verification?.command_success,
    observable: verification?.observable_effect_verified,
    semantic: verification?.semantic_effect_verified,
  };
  Object.entries(values).forEach(([name, value]) => {
    const node = elements.proofOutput.querySelector(`[data-proof="${name}"]`);
    node.dataset.value = value === true ? "true" : value === false ? "false" : "unknown";
  });
  elements.verificationMessage.textContent = verification?.message || "等待验证结果";
}

function eventKind(type) {
  if (["model_request", "model_response", "thinking", "metrics"].includes(type)) return "model";
  if (["action", "execution"].includes(type)) return "action";
  if (["verification"].includes(type)) return "verification";
  if (["recovery", "user_prompt", "user_response"].includes(type)) return "recovery";
  return "system";
}

function eventGlyph(type) {
  if (eventKind(type) === "model") return "M";
  if (eventKind(type) === "action") return "A";
  if (eventKind(type) === "verification") return "V";
  if (eventKind(type) === "recovery") return "R";
  return "·";
}

function summarizeEvent(event) {
  const payload = event.payload || {};
  if (event.type === "phase_change") return payload.reason || event.message;
  if (event.type === "observation") {
    return [payload.current_app, payload.screen_width && `${payload.screen_width}×${payload.screen_height}`]
      .filter(Boolean).join(" · ");
  }
  if (event.type === "model_response") return payload.thinking || event.message;
  if (event.type === "action") return payload.action ? JSON.stringify(payload.action) : event.message;
  if (event.type === "verification") return `${payload.status || ""} · ${payload.policy || ""}`;
  if (event.type === "recovery") return payload.decision?.strategy || event.message;
  if (event.type === "metrics") {
    const metrics = payload.metrics || {};
    return [`${Number(metrics.total_time || 0).toFixed(2)}s`, metrics.total_tokens && `${metrics.total_tokens} tokens`]
      .filter(Boolean).join(" · ");
  }
  return event.message || "事件已记录";
}

function renderEvents() {
  const taskId = appState.snapshot?.task?.id;
  let events = appState.events.filter((event) => taskId ? event.task_id === taskId : !event.task_id);
  if (appState.eventFilter !== "all") {
    events = events.filter((event) => eventKind(event.type) === appState.eventFilter);
  }
  elements.eventCount.textContent = `${events.length} events`;
  elements.eventFeed.replaceChildren();
  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const symbol = document.createElement("span");
    symbol.textContent = "◎";
    const text = document.createElement("p");
    text.textContent = taskId
      ? "当前筛选条件下还没有事件。"
      : "任务运行后，状态迁移和结构化事件会显示在这里。";
    empty.append(symbol, text);
    elements.eventFeed.append(empty);
    return;
  }
  events.slice(-250).forEach((event) => {
    const item = document.createElement("article");
    item.className = "event-item";
    item.dataset.kind = eventKind(event.type);
    const time = document.createElement("span");
    time.className = "event-time";
    time.textContent = formatTime(event.timestamp);
    const marker = document.createElement("span");
    marker.className = "event-marker";
    marker.textContent = eventGlyph(event.type);
    const body = document.createElement("div");
    body.className = "event-body";
    const header = document.createElement("header");
    const title = document.createElement("b");
    title.textContent = eventLabels[event.type] || event.type;
    const step = document.createElement("span");
    const payloadStep = event.payload?.step;
    step.textContent = payloadStep ? `STEP ${payloadStep}` : `#${event.sequence}`;
    header.append(title, step);
    const summary = document.createElement("p");
    summary.textContent = summarizeEvent(event);
    body.append(header, summary);
    if (event.payload && Object.keys(event.payload).length) {
      const details = document.createElement("details");
      const detailsSummary = document.createElement("summary");
      detailsSummary.textContent = "查看结构化数据";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(event.payload, null, 2);
      details.append(detailsSummary, pre);
      body.append(details);
    }
    item.append(time, marker, body);
    elements.eventFeed.append(item);
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
  elements.promptModal.hidden = false;
}

async function fetchState() {
  try {
    const snapshot = await api("/api/state");
    setConnection(true);
    appState.snapshot = snapshot;
    const taskId = snapshot.task.id;
    if (taskId && taskId !== appState.currentTaskId) {
      appState.currentTaskId = taskId;
      appState.events = appState.events.filter((event) => event.task_id === taskId);
    }
    renderChecks(snapshot.startup);
    renderRuntime(snapshot);
    renderTask(snapshot.task);
    renderPrompt(snapshot.pending_prompt);
    elements.sessionClock.textContent = formatClock(Date.now() / 1000 - snapshot.session.started_at);
    if (appState.lastTaskStatus !== snapshot.task.status) {
      if (["success", "failed"].includes(snapshot.task.status)) loadTrajectories();
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
      appState.events = appState.events.slice(-500);
      renderEvents();
    }
    appState.eventCursor = Math.max(appState.eventCursor, payload.cursor || 0);
  } catch (error) {
    // The state poll owns the connection indicator; event polling retries quietly.
  } finally {
    setTimeout(fetchEvents, 550);
  }
}

async function submitTask(event) {
  event.preventDefault();
  const task = elements.taskInput.value.trim();
  if (!task) return;
  elements.runButton.disabled = true;
  try {
    await api("/api/tasks", { method: "POST", body: JSON.stringify({ task }) });
    showToast("任务已提交");
  } catch (error) {
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
    elements.trajectoryList.textContent = `读取轨迹失败：${error.message}`;
  }
}

function renderTrajectoryList() {
  const query = elements.trajectorySearch.value.trim().toLocaleLowerCase();
  const items = appState.trajectories.filter((item) => {
    const haystack = `${item.task || ""} ${item.run_id || ""} ${item.filename || ""}`.toLocaleLowerCase();
    return !query || haystack.includes(query);
  });
  elements.trajectoryList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "trajectory-empty";
    empty.textContent = query ? "没有匹配的轨迹" : "runs 下还没有轨迹";
    elements.trajectoryList.append(empty);
    return;
  }
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "trajectory-item";
    button.dataset.success = item.success === true ? "true" : item.success === false ? "false" : "unknown";
    const dot = document.createElement("i");
    const copy = document.createElement("span");
    const title = document.createElement("b");
    title.textContent = item.task || item.filename;
    const meta = document.createElement("small");
    meta.textContent = `${formatDate(item.started_at)} · ${item.event_count || 0} events`;
    copy.append(title, meta);
    const duration = document.createElement("em");
    duration.textContent = item.duration_seconds == null ? "—" : `${Number(item.duration_seconds).toFixed(1)}s`;
    button.append(dot, copy, duration);
    button.addEventListener("click", () => openTrajectory(item.filename));
    elements.trajectoryList.append(button);
  });
}

async function openTrajectory(filename) {
  try {
    const trajectory = await api(`/api/trajectory?name=${encodeURIComponent(filename)}`);
    elements.trajectoryList.hidden = true;
    elements.trajectorySearch.parentElement.hidden = true;
    elements.trajectoryDetail.hidden = false;
    elements.trajectoryResult.dataset.success = String(trajectory.success);
    elements.trajectoryResult.textContent = trajectory.success ? "SUCCESS" : "FAILED";
    elements.trajectoryTask.textContent = trajectory.task || "未命名任务";
    elements.downloadTrajectory.href = `/api/trajectory?name=${encodeURIComponent(filename)}&download=1`;
    elements.trajectoryMeta.replaceChildren();
    [
      `RUN ${String(trajectory.run_id || "").slice(0, 10)}`,
      `${Number(trajectory.duration_seconds || 0).toFixed(2)}s`,
      `${trajectory.event_count || 0} events`,
      `schema ${trajectory.schema_version || "—"}`,
    ].forEach((text) => {
      const chip = document.createElement("span");
      chip.textContent = text;
      elements.trajectoryMeta.append(chip);
    });
    elements.trajectoryEvents.replaceChildren();
    const events = trajectory.events || [];
    const visible = events.slice(-300);
    if (events.length > visible.length) {
      const notice = document.createElement("div");
      notice.className = "trajectory-empty";
      notice.textContent = `事件较多，仅展示最后 ${visible.length} 条；可下载完整 JSON。`;
      elements.trajectoryEvents.append(notice);
    }
    visible.forEach((event) => {
      const row = document.createElement("div");
      row.className = "trajectory-event";
      const step = document.createElement("span");
      step.textContent = event.step == null ? "—" : String(event.step).padStart(2, "0");
      const copy = document.createElement("div");
      const title = document.createElement("b");
      title.textContent = eventLabels[event.type] || event.type;
      const message = document.createElement("p");
      message.textContent = event.message || summarizeEvent(event);
      copy.append(title, message);
      row.append(step, copy);
      elements.trajectoryEvents.append(row);
    });
  } catch (error) {
    showToast(error.message);
  }
}

function closeTrajectory() {
  elements.trajectoryDetail.hidden = true;
  elements.trajectoryList.hidden = false;
  elements.trajectorySearch.parentElement.hidden = false;
}

elements.taskForm.addEventListener("submit", submitTask);
elements.taskInput.addEventListener("input", () => {
  const task = appState.snapshot?.task;
  const ready = appState.snapshot?.startup?.status === "ready";
  const busy = task && ["running", "waiting_user"].includes(task.status);
  elements.runButton.disabled = !ready || busy || !elements.taskInput.value.trim();
});
document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.taskInput.value = button.dataset.example;
    elements.taskInput.dispatchEvent(new Event("input"));
    elements.taskInput.focus();
  });
});
document.querySelectorAll("[data-event-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-event-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    appState.eventFilter = button.dataset.eventFilter;
    renderEvents();
  });
});
elements.recheckButton.addEventListener("click", rerunChecks);
elements.rejectPrompt.addEventListener("click", () => respondToPrompt(false));
elements.acceptPrompt.addEventListener("click", () => respondToPrompt(true));
elements.refreshTrajectories.addEventListener("click", loadTrajectories);
elements.trajectorySearch.addEventListener("input", renderTrajectoryList);
elements.closeTrajectory.addEventListener("click", closeTrajectory);

fetchState();
fetchEvents();
loadTrajectories();
