"use strict";

const busyTaskStatuses = new Set(["running", "waiting_user", "cancelling"]);

export const taskLabels = {
  idle: "空闲",
  running: "执行中",
  waiting_user: "等待你操作",
  cancelling: "正在停止",
  success: "已完成",
  failed: "未完成",
  cancelled: "已停止",
};

export const phaseLabels = {
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

export function createAppState() {
  return {
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
}

export function isTaskBusy(status) {
  return busyTaskStatuses.has(status);
}
