"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function formatTokens(value) {
  return value === null ? "—" : new Intl.NumberFormat("zh-CN").format(Math.round(value));
}

export function usageSamples(events, pricing) {
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
    svg.append(svgNode("line", {
      x1: left, y1: y, x2: right, y2: y, class: "usage-grid-line",
    }));
    svg.append(svgNode("text", {
      x: left - 8, y: y + 3, class: "usage-axis-label", "text-anchor": "end",
    }, formatTokens(maxTokens * (1 - ratio))));
    svg.append(svgNode("text", {
      x: right + 8, y: y + 3, class: "usage-axis-label", "text-anchor": "start",
    }, `${(maxTime * (1 - ratio)).toFixed(1)}s`));
  }

  svg.append(svgNode("text", { x: left, y: 16, class: "usage-series-label token" }, "总 Token"));
  svg.append(svgNode("text", {
    x: right, y: 16, class: "usage-series-label time", "text-anchor": "end",
  }, "模型耗时"));
  const tokenPoints = metricPoints(samples, xFor, tokenY, "totalTokens");
  const timePoints = metricPoints(samples, xFor, timeY, "totalTime");
  if (tokenPoints) {
    svg.append(svgNode("polyline", { points: tokenPoints, class: "usage-line token" }));
  }
  if (timePoints) {
    svg.append(svgNode("polyline", { points: timePoints, class: "usage-line time" }));
  }

  samples.forEach((sample, index) => {
    const x = xFor(index);
    if (sample.totalTokens !== null) {
      const point = svgNode("circle", {
        cx: x, cy: tokenY(sample.totalTokens), r: 4, class: "usage-point token",
      });
      point.append(svgNode(
        "title", {}, `请求 ${sample.request}：${formatTokens(sample.totalTokens)} Token`,
      ));
      svg.append(point);
    }
    if (sample.totalTime !== null) {
      const point = svgNode("circle", {
        cx: x, cy: timeY(sample.totalTime), r: 4, class: "usage-point time",
      });
      point.append(svgNode(
        "title", {}, `请求 ${sample.request}：${sample.totalTime.toFixed(2)} 秒`,
      ));
      svg.append(point);
    }
    svg.append(svgNode("text", {
      x, y: bottom + 22, class: "usage-x-label", "text-anchor": "middle",
    }, `#${sample.request}`));
  });

  if (hasCost) {
    const costTop = 245;
    const costBottom = 292;
    const maxCost = Math.max(0.000001, ...samples.map((sample) => sample.cost || 0));
    const costY = (value) => costBottom - (value / maxCost) * (costBottom - costTop);
    svg.append(svgNode("line", {
      x1: left, y1: costBottom, x2: right, y2: costBottom, class: "usage-grid-line",
    }));
    svg.append(svgNode("text", {
      x: left, y: costTop - 10, class: "usage-series-label cost",
    }, `单次费用 · ${pricing.currency}`));
    const costPoints = metricPoints(samples, xFor, costY, "cost");
    if (costPoints) {
      svg.append(svgNode("polyline", { points: costPoints, class: "usage-line cost" }));
    }
    samples.forEach((sample, index) => {
      if (sample.cost === null) return;
      const point = svgNode("circle", {
        cx: xFor(index), cy: costY(sample.cost), r: 3.5, class: "usage-point cost",
      });
      point.append(svgNode(
        "title", {}, `请求 ${sample.request}：${pricing.currency} ${sample.cost.toFixed(6)}`,
      ));
      svg.append(point);
    });
  }

  const breakdown = document.createElement("div");
  breakdown.className = "usage-breakdown";
  samples.forEach((sample) => {
    const item = document.createElement("span");
    const costText = sample.cost === null
      ? ""
      : ` · ${pricing.currency} ${sample.cost.toFixed(6)}`;
    const timeText = sample.totalTime === null ? "—" : `${sample.totalTime.toFixed(1)}s`;
    item.textContent = `#${sample.request}  ${formatTokens(sample.totalTokens)} tok · ${timeText}${costText}`;
    breakdown.append(item);
  });
  target.replaceChildren(svg, breakdown);
}

export function renderUsagePanel(events, status, panel, summary, chart, note, pricing = {}) {
  const finished = ["success", "failed", "cancelled"].includes(status);
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
