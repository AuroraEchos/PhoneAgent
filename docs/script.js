"use strict";

/*
 * Update this one value after creating the public GitHub repository.
 * All repository, release, issue, README, license, and clone links are derived from it.
 */
const SITE_CONFIG = {
  repositoryUrl: "https://github.com/AuroraEchos/PhoneAgent",
  defaultLanguage: "en",
};

const translations = {
  en: {
    "nav.features": "Features",
    "nav.architecture": "Architecture",
    "nav.quickstart": "Quick Start",
    "nav.roadmap": "Roadmap",
    "nav.limitations": "Limitations",
    "ecosystem.kicker": "Open-source lineage",
    "ecosystem.description": "Inspired by Open-AutoGLM and recommended with Zhipu BigModel's autoglm-phone API.",
    "ecosystem.inspiration": "Project inspiration",
    "provider.kicker": "Recommended provider",
    "provider.apikey": "Apply on the Zhipu platform",
    "backToTop": "Back to top",
    "hero.eyebrow": "Open source · v0.1.1 Alpha",
    "hero.titleLine1": "An Android agent runtime",
    "hero.titleLine2": "that can see what it does.",
    "hero.description": "PhoneAgent combines vision-language planning, deterministic Android capabilities, safe structured actions, post-action evidence, and bounded recovery into one auditable loop for real devices.",
    "hero.github": "View on GitHub",
    "hero.start": "Get started",
    "hero.meta.runtime": "Runtime",
    "hero.meta.target": "Target",
    "hero.meta.license": "License",
    "demo.task": "Open WeChat and order a coffee in Meituan.",
    "features.kicker": "Core capabilities",
    "features.title": "A small runtime with explicit trust boundaries.",
    "features.description": "PhoneAgent keeps each layer inspectable: observation, model planning, action parsing, Android execution, evidence verification, recovery, and trajectory persistence.",
    "features.vision.title": "Vision-first grounding",
    "features.vision.description": "The planner reasons from the current screenshot instead of requiring an accessibility tree, enabling interaction with text, icons, and visually defined controls.",
    "features.protocol.title": "Safe action protocol",
    "features.protocol.description": "Model output is parsed through AST/JSON and validated against an action allow-list. Generated text is never executed as Python code; actions marked or detected as sensitive require confirmation.",
    "features.resolver.title": "Deterministic app routing",
    "features.resolver.description": "Discover Launcher activities and resolve aliases. High-confidence pure launch tasks can bypass the VLM; multi-step tasks receive app context and continue through the visual loop.",
    "features.verify.title": "Evidence-aware verification",
    "features.verify.description": "Separate command success, observable UI change, and deterministic semantic evidence instead of collapsing them into one success flag.",
    "features.recovery.title": "Bounded recovery",
    "features.recovery.description": "Failure episodes have explicit budgets. Non-idempotent actions such as Tap, Type, Swipe, and Back are never blindly replayed.",
    "features.trajectory.title": "Auditable trajectories",
    "features.trajectory.description": "Persist observation metadata, model responses, actions, execution evidence, verification, recovery decisions, state transitions, and final results.",
    "architecture.kicker": "Architecture",
    "architecture.title": "Deterministic where possible. Visual where necessary.",
    "architecture.description": "Only a high-confidence pure open-app goal takes the deterministic launch shortcut. Other tasks follow an explicit observe, plan, execute, verify, and recover state machine.",
    "architecture.point1.title": "App-aware initialization",
    "architecture.point1.description": "Discover Launcher activities, apply aliases, and provide likely goal apps to the planner.",
    "architecture.point2.title": "One-action loop",
    "architecture.point2.description": "Observe a screenshot, request one model action, validate it, and dispatch it to the action handler and ADB device layer.",
    "architecture.point3.title": "Evidence and recovery",
    "architecture.point3.description": "Verify the result, then continue, replan, or retry only safe actions within explicit budgets.",
    "architecture.read": "Read the architecture document",
    "quickstart.kicker": "Quick Start",
    "quickstart.title": "From clone to first run.",
    "quickstart.description": "No frontend build step, no workflow framework, and no device-specific accessibility tree required.",
    "quickstart.step1.title": "Prepare the environment",
    "quickstart.step1.description": "Python 3.12+, uv, Android Platform Tools, and a USB-debuggable device. Install ADB Keyboard before tasks that use Type.",
    "quickstart.step2.title": "Configure the model",
    "quickstart.step2.description": "Use a vision-language model service compatible with the OpenAI Chat Completions API.",
    "quickstart.step3.title": "Run a task",
    "quickstart.step3.description": "Run a multi-step WeChat and Meituan task. The planner is instructed to mark order submission as sensitive so the runtime requests confirmation.",
    "quickstart.copy": "Copy",
    "quickstart.copied": "Copied",
    "quickstart.result": "ADB preflight passed · model API responded · task started",
    "trajectory.kicker": "Traceability",
    "trajectory.title": "Significant runtime transitions leave evidence.",
    "trajectory.description": "A run is not just terminal output. PhoneAgent records the state machine, model interaction, structured action, execution result, verification evidence, recovery policy, and final outcome.",
    "trajectory.item1": "Investigate failed runs through structured state, action, and evidence events.",
    "trajectory.item2": "Measure latency, actions, and recovery behavior; capture tokens when the provider reports usage.",
    "trajectory.item3": "Use saved trajectories as input for evaluation and future experience-learning work.",
    "trajectory.release": "Read the v0.1.1 release notes",
    "roadmap.kicker": "Roadmap",
    "roadmap.title": "The runtime is small by design. The direction is not.",
    "roadmap.description": "The first release freezes a reliable baseline. Future work can improve semantic correctness without obscuring the core loop.",
    "roadmap.complete": "Released",
    "roadmap.next": "Next",
    "roadmap.future": "Longer term",
    "roadmap.item1.title": "Vision agent loop",
    "roadmap.item1.description": "Observe, plan, execute, verify, recover.",
    "roadmap.item2.title": "Android app resolver",
    "roadmap.item2.description": "Discovery, aliases, package launch.",
    "roadmap.item3.title": "Safe action runtime",
    "roadmap.item3.description": "Validation, confirmation, bounded recovery.",
    "roadmap.web.title": "Local Web Console",
    "roadmap.web.description": "Session checks, live events, prompts, and trajectory inspection.",
    "roadmap.item4.title": "Broader semantic verification",
    "roadmap.item4.description": "Subgoal-aware evidence and independent review beyond deterministic system checks.",
    "roadmap.item5.title": "Evaluation harness",
    "roadmap.item5.description": "Task suites, replay, metrics, and regression.",
    "roadmap.item6.title": "Provider abstraction",
    "roadmap.item6.description": "More local and hosted VLM backends.",
    "roadmap.item7.title": "On-device runtime",
    "roadmap.item7.description": "Accessibility, MediaProjection, privacy controls.",
    "roadmap.item8.title": "Experience learning",
    "roadmap.item8.description": "Reusable app knowledge from trajectories.",
    "roadmap.item9.title": "Hybrid perception",
    "roadmap.item9.description": "Vision plus system UI signals where available.",
    "limitations.kicker": "Current boundaries",
    "limitations.title": "Honest about what v0.1.1 can prove.",
    "limitations.description": "PhoneAgent is an Alpha research and engineering runtime. It exposes uncertainty instead of converting weak evidence into confident claims.",
    "limitations.item1.title": "Visual change is not semantic correctness",
    "limitations.item1.description": "For coordinate actions, a changed screen does not prove that the intended UI target was selected.",
    "limitations.item2.title": "Task completion is model-reported",
    "limitations.item2.description": "The planner currently reports full completion through finish(...); there is no independent task judge yet.",
    "limitations.item3.title": "Protected screens may require takeover",
    "limitations.item3.description": "The runtime does not guess on blank or protected screens; it requests takeover when enabled or stops the run.",
    "limitations.item4.title": "ADB is the current deployment boundary",
    "limitations.item4.description": "A true on-device product requires an Android application, services, permissions, and privacy controls.",
    "cta.kicker": "Build with PhoneAgent",
    "cta.title": "A transparent baseline for Android agents.",
    "cta.description": "Read the code, reproduce the loop, inspect the trajectory, and help improve reliable mobile interaction.",
    "cta.github": "Explore the repository",
    "cta.issue": "Open an issue",
    "footer.description": "Vision-driven Android agent runtime.",
    "footer.project": "Project",
    "footer.resources": "Resources",
    "toast.copied": "Copied to clipboard",
  },
  zh: {
    "nav.features": "核心能力",
    "nav.architecture": "系统架构",
    "nav.quickstart": "快速开始",
    "nav.roadmap": "开发路线",
    "nav.limitations": "能力边界",
    "ecosystem.kicker": "开源项目致谢",
    "ecosystem.description": "项目早期受到 Open-AutoGLM 启发，并推荐使用智谱 BigModel 的 autoglm-phone API。",
    "ecosystem.inspiration": "项目启发来源",
    "provider.kicker": "推荐模型服务",
    "provider.apikey": "在智谱开放平台申请",
    "backToTop": "返回顶部",
    "hero.eyebrow": "开源项目 · v0.1.1 Alpha",
    "hero.titleLine1": "一个能够看见执行结果的",
    "hero.titleLine2": "Android Agent Runtime。",
    "hero.description": "PhoneAgent 将视觉语言规划、Android 确定性能力、安全结构化动作、动作后证据验证和有界恢复整合为一条面向真实设备、可审计的执行闭环。",
    "hero.github": "查看 GitHub",
    "hero.start": "快速开始",
    "hero.meta.runtime": "运行环境",
    "hero.meta.target": "目标设备",
    "hero.meta.license": "开源协议",
    "demo.task": "打开微信，并在美团小程序中下单一杯咖啡。",
    "features.kicker": "核心能力",
    "features.title": "保持核心轻量，同时明确每一层的可信边界。",
    "features.description": "PhoneAgent 将观察、模型规划、动作解析、Android 执行、证据验证、恢复决策和轨迹持久化拆分为可检查的独立层。",
    "features.vision.title": "纯视觉界面定位",
    "features.vision.description": "规划模型直接根据当前截图推理，无需依赖 Accessibility Tree，可操作文字、图标以及其他视觉定义的控件。",
    "features.protocol.title": "安全动作协议",
    "features.protocol.description": "模型输出通过 AST/JSON 解析，并经过动作白名单与参数验证；系统不会执行模型生成的 Python 代码，被标记或检测为敏感的动作需要用户确认。",
    "features.resolver.title": "确定性应用路由",
    "features.resolver.description": "动态发现 Launcher Activity 并解析应用别名。高置信度的纯启动任务可绕过视觉模型；多步骤任务则获得应用上下文后继续进入视觉闭环。",
    "features.verify.title": "基于证据的验证",
    "features.verify.description": "分别表达命令执行成功、界面可观察变化和确定性语义证据，避免将三者压缩成一个模糊的成功标志。",
    "features.recovery.title": "有界恢复机制",
    "features.recovery.description": "连续失败拥有明确预算；Tap、Type、Swipe、Back 等非幂等动作不会被运行时盲目重放。",
    "features.trajectory.title": "可审计执行轨迹",
    "features.trajectory.description": "持久化观察元数据、模型响应、动作、执行证据、验证结果、恢复决策、状态迁移和最终结果。",
    "architecture.kicker": "系统架构",
    "architecture.title": "能够确定时走系统路径，必须理解时再使用视觉。",
    "architecture.description": "只有高置信度的纯打开应用目标会采用确定性启动捷径；其他任务严格进入观察、规划、执行、验证与恢复状态机。",
    "architecture.point1.title": "应用感知初始化",
    "architecture.point1.description": "发现 Launcher Activity、应用别名，并向规划模型提供可能相关的目标应用。",
    "architecture.point2.title": "单动作闭环",
    "architecture.point2.description": "获取截图、请求一个模型动作并完成协议校验，再交给动作处理器与 ADB 设备层执行。",
    "architecture.point3.title": "证据与恢复",
    "architecture.point3.description": "验证动作结果，再决定继续、重新规划，或在预算内仅重试安全动作。",
    "architecture.read": "阅读完整架构说明",
    "quickstart.kicker": "快速开始",
    "quickstart.title": "从克隆仓库到运行第一个任务。",
    "quickstart.description": "不需要前端构建、不依赖工作流框架，也不要求特定厂商的 Accessibility Tree。",
    "quickstart.step1.title": "准备运行环境",
    "quickstart.step1.description": "准备 Python 3.12+、uv、Android Platform Tools 和开启 USB 调试的真机；包含 Type 的任务还需安装 ADB Keyboard。",
    "quickstart.step2.title": "配置视觉模型",
    "quickstart.step2.description": "接入兼容 OpenAI Chat Completions API 的视觉语言模型服务。",
    "quickstart.step3.title": "执行自然语言任务",
    "quickstart.step3.description": "运行微信与美团的多步骤任务；系统提示词要求规划模型将提交订单标记为敏感动作，运行时据此请求用户确认。",
    "quickstart.copy": "复制",
    "quickstart.copied": "已复制",
    "quickstart.result": "ADB 预检通过 · 模型 API 已响应 · 任务已启动",
    "trajectory.kicker": "执行可追溯",
    "trajectory.title": "关键运行时状态都会留下证据。",
    "trajectory.description": "一次运行不只是终端输出。PhoneAgent 会记录状态机、模型交互、结构化动作、执行结果、验证证据、恢复策略以及最终状态。",
    "trajectory.item1": "通过结构化的状态、动作与证据事件，定位和复盘失败运行。",
    "trajectory.item2": "统计延迟、动作与恢复行为；模型服务返回 usage 时记录 Token。",
    "trajectory.item3": "将保存的轨迹作为后续评估与经验学习工作的输入。",
    "trajectory.release": "阅读 v0.1.1 发布说明",
    "roadmap.kicker": "开发路线",
    "roadmap.title": "核心运行时刻意保持简单，但发展方向并不狭窄。",
    "roadmap.description": "首个版本冻结一条可靠基线。后续将在不掩盖核心闭环的前提下增强语义正确性。",
    "roadmap.complete": "已经发布",
    "roadmap.next": "下一阶段",
    "roadmap.future": "长期研究",
    "roadmap.item1.title": "视觉 Agent Loop",
    "roadmap.item1.description": "观察、规划、执行、验证和恢复。",
    "roadmap.item2.title": "Android 应用解析",
    "roadmap.item2.description": "动态发现、别名和 package 启动。",
    "roadmap.item3.title": "安全动作运行时",
    "roadmap.item3.description": "参数校验、敏感确认和有界恢复。",
    "roadmap.web.title": "本地 Web Console",
    "roadmap.web.description": "会话预检、实时事件、交互确认和轨迹检查。",
    "roadmap.item4.title": "更广泛的语义验证",
    "roadmap.item4.description": "在确定性系统检查之外，引入子目标证据与独立任务评审。",
    "roadmap.item5.title": "评估体系",
    "roadmap.item5.description": "任务集、轨迹回放、指标和回归测试。",
    "roadmap.item6.title": "模型服务抽象",
    "roadmap.item6.description": "支持更多本地及托管视觉模型后端。",
    "roadmap.item7.title": "端侧运行时",
    "roadmap.item7.description": "Accessibility、MediaProjection 与隐私控制。",
    "roadmap.item8.title": "经验学习",
    "roadmap.item8.description": "从轨迹中沉淀可复用的应用操作知识。",
    "roadmap.item9.title": "混合感知",
    "roadmap.item9.description": "在可用时结合视觉与系统 UI 信号。",
    "limitations.kicker": "当前能力边界",
    "limitations.title": "如实表达 v0.1.1 能够证明什么。",
    "limitations.description": "PhoneAgent 当前是 Alpha 阶段的研究与工程运行时。它会显式暴露不确定性，而不是把弱证据包装成确定结论。",
    "limitations.item1.title": "画面变化不等于语义正确",
    "limitations.item1.description": "对于坐标动作，界面发生变化不能证明模型选择了语义上正确的目标。",
    "limitations.item2.title": "任务完成由规划模型报告",
    "limitations.item2.description": "目前由模型通过 finish(...) 报告完整任务结束，尚未引入独立任务评审器。",
    "limitations.item3.title": "受保护页面可能需要人工接管",
    "limitations.item3.description": "运行时不会在黑屏或受保护页面上猜测坐标；允许时请求人工接管，否则终止运行。",
    "limitations.item4.title": "当前部署边界仍然是 ADB",
    "limitations.item4.description": "真正端侧产品还需要 Android 应用、系统服务、权限管理与完整隐私控制。",
    "cta.kicker": "使用 PhoneAgent 构建",
    "cta.title": "一条透明、可复现的 Android Agent 基线。",
    "cta.description": "阅读源码、复现执行闭环、检查轨迹，并共同改进可靠的手机界面交互。",
    "cta.github": "浏览项目仓库",
    "cta.issue": "提交 Issue",
    "footer.description": "视觉驱动的 Android Agent Runtime。",
    "footer.project": "项目",
    "footer.resources": "资源",
    "toast.copied": "已复制到剪贴板",
  },
};

const normalizeRepositoryUrl = (url) => url.replace(/\/$/, "");
const repositoryUrl = normalizeRepositoryUrl(SITE_CONFIG.repositoryUrl);

const derivedLinks = {
  github: repositoryUrl,
  release: `${repositoryUrl}/releases/tag/v0.1.1`,
  issues: `${repositoryUrl}/issues`,
  readme: `${repositoryUrl}#readme`,
  license: `${repositoryUrl}/blob/main/LICENSE`,
  architecture: `${repositoryUrl}/blob/main/docs/ARCHITECTURE.md`,
};

function applyRepositoryLinks() {
  document.querySelectorAll("[data-link]").forEach((element) => {
    const key = element.dataset.link;
    if (derivedLinks[key]) element.href = derivedLinks[key];
  });

  document.querySelectorAll("[data-repository-clone]").forEach((element) => {
    element.textContent = `${repositoryUrl}.git`;
  });
}

function readStoredLanguage() {
  try {
    return localStorage.getItem("phoneagent-language");
  } catch {
    return null;
  }
}

function writeStoredLanguage(language) {
  try {
    localStorage.setItem("phoneagent-language", language);
  } catch {
    // Storage can be unavailable in hardened browser contexts. The page still works.
  }
}

const browserLanguage = navigator.language?.toLowerCase().startsWith("zh") ? "zh" : null;
let currentLanguage = readStoredLanguage() || browserLanguage || SITE_CONFIG.defaultLanguage;
if (!translations[currentLanguage]) currentLanguage = "en";

function applyLanguage(language) {
  currentLanguage = language;
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";

  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const key = element.dataset.i18n;
    const value = translations[language][key];
    if (value !== undefined) element.textContent = value;
  });

  const languageLabel = document.querySelector("[data-language-label]");
  if (languageLabel) languageLabel.textContent = language === "en" ? "中文" : "EN";

  const languageToggle = document.querySelector("[data-language-toggle]");
  if (languageToggle) {
    languageToggle.setAttribute(
      "aria-label",
      language === "en" ? "切换到中文" : "Switch to English",
    );
  }

  const toast = document.querySelector("[data-toast]");
  if (toast) toast.textContent = translations[language]["toast.copied"];

  const backToTop = document.querySelector("[data-back-to-top]");
  if (backToTop) backToTop.setAttribute("aria-label", translations[language].backToTop);

  writeStoredLanguage(language);
}

function setupLanguageToggle() {
  const button = document.querySelector("[data-language-toggle]");
  if (!button) return;
  button.addEventListener("click", () => {
    applyLanguage(currentLanguage === "en" ? "zh" : "en");
  });
}

function setupHeader() {
  const header = document.querySelector("[data-header]");
  const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 18);
  updateHeader();
  window.addEventListener("scroll", updateHeader, { passive: true });
}

function setupNavigation() {
  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  if (!toggle || !nav) return;

  const close = () => {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!open));
    nav.classList.toggle("open", !open);
  });

  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
  document.addEventListener("click", (event) => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) close();
  });
}

function setupRevealAnimations() {
  const elements = document.querySelectorAll(".reveal");
  if (!elements.length) return;

  if (!("IntersectionObserver" in window)) {
    elements.forEach((element) => element.classList.add("visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      });
    },
    { threshold: 0.13, rootMargin: "0px 0px -40px" },
  );

  elements.forEach((element) => observer.observe(element));
}

function setupCopyButtons() {
  document.querySelectorAll("[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const text = target.innerText;

      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }

      const label = button.querySelector("[data-copy-label]");
      if (label) {
        const original = translations[currentLanguage]["quickstart.copy"];
        label.textContent = translations[currentLanguage]["quickstart.copied"];
        window.setTimeout(() => { label.textContent = original; }, 1500);
      }
      showToast();
    });
  });
}

let toastTimer;
function showToast() {
  const toast = document.querySelector("[data-toast]");
  if (!toast) return;
  window.clearTimeout(toastTimer);
  toast.classList.add("visible");
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 1800);
}

function setupScrollProgress() {
  const bar = document.querySelector("[data-scroll-progress]");
  if (!bar) return;

  const update = () => {
    const scrollable = document.documentElement.scrollHeight - window.innerHeight;
    const progress = scrollable > 0 ? Math.min(window.scrollY / scrollable, 1) : 0;
    bar.style.transform = `scaleX(${progress})`;
  };

  update();
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update, { passive: true });
}

function setupActiveNavigation() {
  const links = [...document.querySelectorAll("[data-nav-link]")];
  if (!links.length || !("IntersectionObserver" in window)) return;

  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  const setActive = (id) => {
    links.forEach((link) => {
      const active = link.getAttribute("href") === `#${id}`;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target?.id) setActive(visible.target.id);
    },
    { rootMargin: "-28% 0px -58%", threshold: [0.05, 0.2, 0.45] },
  );

  sections.forEach((section) => observer.observe(section));
}

function setupSpotlights() {
  if (window.matchMedia("(pointer: coarse)").matches) return;

  document.querySelectorAll("[data-spotlight]").forEach((element) => {
    element.addEventListener("pointermove", (event) => {
      const rect = element.getBoundingClientRect();
      element.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`);
      element.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`);
      element.classList.add("spotlight-active");
    });
    element.addEventListener("pointerleave", () => element.classList.remove("spotlight-active"));
  });
}

function setupBackToTop() {
  const button = document.querySelector("[data-back-to-top]");
  if (!button) return;

  const update = () => button.classList.toggle("visible", window.scrollY > 720);
  button.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  update();
  window.addEventListener("scroll", update, { passive: true });
}

function setupRuntimeDemo() {
  const steps = [...document.querySelectorAll("[data-demo-step]")];
  if (steps.length < 2) return;

  let processingIndex = steps.length - 1;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const render = () => {
    steps.forEach((step, index) => {
      const indicator = step.querySelector("[data-demo-indicator]");
      const isDone = index < processingIndex;
      const isProcessing = index === processingIndex;

      step.classList.toggle("active", isDone);
      step.classList.toggle("processing", isProcessing);
      step.classList.toggle("pending", !isDone && !isProcessing);

      if (!indicator) return;
      indicator.className = "demo-indicator";
      indicator.textContent = "";

      if (isDone) {
        indicator.classList.add("step-state");
        indicator.textContent = "done";
      } else if (isProcessing) {
        indicator.classList.add("spinner");
      } else {
        indicator.classList.add("step-pending");
        indicator.textContent = "·";
      }
    });
  };

  render();
  if (reducedMotion) return;

  window.setInterval(() => {
    processingIndex = (processingIndex + 1) % steps.length;
    render();
  }, 1800);
}

function setupHeroParallax() {
  const visual = document.querySelector(".hero-visual");
  const phone = document.querySelector(".phone-frame");
  if (!visual || !phone || window.matchMedia("(pointer: coarse)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  visual.addEventListener("pointermove", (event) => {
    const rect = visual.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    phone.style.setProperty("--parallax-x", `${x * 5}deg`);
    phone.style.setProperty("--parallax-y", `${y * -3}deg`);
  });

  visual.addEventListener("pointerleave", () => {
    phone.style.removeProperty("--parallax-x");
    phone.style.removeProperty("--parallax-y");
  });
}

function setupCurrentYear() {
  document.querySelectorAll("[data-current-year]").forEach((element) => {
    element.textContent = String(new Date().getFullYear());
  });
}

applyRepositoryLinks();
applyLanguage(currentLanguage);
setupLanguageToggle();
setupHeader();
setupNavigation();
setupScrollProgress();
setupActiveNavigation();
setupSpotlights();
setupBackToTop();
setupRuntimeDemo();
setupHeroParallax();
setupRevealAnimations();
setupCopyButtons();
setupCurrentYear();
