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
    "hero.eyebrow": "Open source · v0.1.0 Alpha",
    "hero.titleLine1": "An Android agent runtime",
    "hero.titleLine2": "that can see what it does.",
    "hero.description": "PhoneAgent combines vision-language planning, deterministic Android capabilities, safe structured actions, post-action evidence, and bounded recovery into one auditable loop for real devices.",
    "hero.github": "View on GitHub",
    "hero.start": "Get started",
    "hero.meta.runtime": "Runtime",
    "hero.meta.target": "Target",
    "hero.meta.license": "License",
    "demo.task": "Open Settings and find Battery.",
    "features.kicker": "Core capabilities",
    "features.title": "A small runtime with explicit trust boundaries.",
    "features.description": "PhoneAgent keeps each layer inspectable: observation, model planning, action parsing, Android execution, evidence verification, recovery, and trajectory persistence.",
    "features.vision.title": "Vision-first grounding",
    "features.vision.description": "The planner reasons from the current screenshot instead of requiring an accessibility tree, enabling interaction with text, icons, and visually defined controls.",
    "features.protocol.title": "Safe action protocol",
    "features.protocol.description": "Model output is parsed through AST/JSON and validated against an action allow-list. Generated text is never executed as Python code.",
    "features.resolver.title": "Deterministic app routing",
    "features.resolver.description": "Discover Launcher activities, resolve aliases, and prefer package/activity launch before falling back to visual navigation.",
    "features.verify.title": "Evidence-aware verification",
    "features.verify.description": "Separate command success, observable UI change, and deterministic semantic evidence instead of collapsing them into one success flag.",
    "features.recovery.title": "Bounded recovery",
    "features.recovery.description": "Failure episodes have explicit budgets. Non-idempotent actions such as Tap, Type, Swipe, and Back are never blindly replayed.",
    "features.trajectory.title": "Auditable trajectories",
    "features.trajectory.description": "Persist observations, model responses, actions, execution evidence, verification, recovery decisions, state transitions, and final results.",
    "architecture.kicker": "Architecture",
    "architecture.title": "Deterministic where possible. Visual where necessary.",
    "architecture.description": "PhoneAgent does not force every operation through a vision model. It combines Android system capabilities with a visual planning loop, then records evidence at each boundary.",
    "architecture.point1.title": "Fast path",
    "architecture.point1.description": "Resolve and launch installed applications through package/activity state.",
    "architecture.point2.title": "General path",
    "architecture.point2.description": "Use the screenshot and task context to plan navigation inside an application.",
    "architecture.point3.title": "Evidence path",
    "architecture.point3.description": "Verify observable or deterministic effects before continuing or recovering.",
    "architecture.read": "Read the architecture document",
    "quickstart.kicker": "Quick Start",
    "quickstart.title": "From clone to first run.",
    "quickstart.description": "No frontend build step, no workflow framework, and no device-specific accessibility tree required.",
    "quickstart.step1.title": "Prepare the environment",
    "quickstart.step1.description": "Linux, Python 3.12+, Android Platform Tools, and an Android device with USB debugging enabled.",
    "quickstart.step2.title": "Configure the model",
    "quickstart.step2.description": "Use a vision-language model service compatible with the OpenAI Chat Completions API.",
    "quickstart.step3.title": "Run a task",
    "quickstart.step3.description": "Start with deterministic application launch, then move to multi-step visual tasks.",
    "quickstart.copy": "Copy",
    "quickstart.copied": "Copied",
    "quickstart.result": "Runtime started · device connected · task initialized",
    "trajectory.kicker": "Traceability",
    "trajectory.title": "Every decision leaves evidence.",
    "trajectory.description": "A run is not just terminal output. PhoneAgent records the state machine, model interaction, structured action, execution result, verification evidence, recovery policy, and final outcome.",
    "trajectory.item1": "Reconstruct failed runs without relying on screenshots alone.",
    "trajectory.item2": "Measure model latency, token usage, action frequency, and recovery behavior.",
    "trajectory.item3": "Build reproducible evaluation and future experience-learning pipelines.",
    "trajectory.release": "Read the v0.1.0 release notes",
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
    "roadmap.item4.title": "Semantic verification",
    "roadmap.item4.description": "Subgoal-aware evidence and independent review.",
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
    "limitations.title": "Honest about what v0.1.0 can prove.",
    "limitations.description": "PhoneAgent is an Alpha research and engineering runtime. It exposes uncertainty instead of converting weak evidence into confident claims.",
    "limitations.item1.title": "Visual change is not semantic correctness",
    "limitations.item1.description": "For coordinate actions, a changed screen does not prove that the intended UI target was selected.",
    "limitations.item2.title": "Task completion is model-reported",
    "limitations.item2.description": "The planner currently reports full completion through finish(...); there is no independent task judge yet.",
    "limitations.item3.title": "Protected screens require takeover",
    "limitations.item3.description": "DRM, FLAG_SECURE, passwords, verification codes, and payment flows may be unobservable or sensitive.",
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
    "hero.eyebrow": "开源项目 · v0.1.0 Alpha",
    "hero.titleLine1": "一个能够看见执行结果的",
    "hero.titleLine2": "Android Agent Runtime。",
    "hero.description": "PhoneAgent 将视觉语言规划、Android 确定性能力、安全结构化动作、动作后证据验证和有界恢复整合为一条面向真实设备、可审计的执行闭环。",
    "hero.github": "查看 GitHub",
    "hero.start": "快速开始",
    "hero.meta.runtime": "运行环境",
    "hero.meta.target": "目标设备",
    "hero.meta.license": "开源协议",
    "demo.task": "打开设置，然后找到电池选项。",
    "features.kicker": "核心能力",
    "features.title": "保持核心轻量，同时明确每一层的可信边界。",
    "features.description": "PhoneAgent 将观察、模型规划、动作解析、Android 执行、证据验证、恢复决策和轨迹持久化拆分为可检查的独立层。",
    "features.vision.title": "纯视觉界面定位",
    "features.vision.description": "规划模型直接根据当前截图推理，无需依赖 Accessibility Tree，可操作文字、图标以及其他视觉定义的控件。",
    "features.protocol.title": "安全动作协议",
    "features.protocol.description": "模型输出通过 AST/JSON 解析，并经过动作白名单与参数验证；系统不会执行模型生成的 Python 代码。",
    "features.resolver.title": "确定性应用路由",
    "features.resolver.description": "动态发现 Launcher Activity、解析应用别名，并优先使用 package/activity 启动，必要时再回退到视觉导航。",
    "features.verify.title": "基于证据的验证",
    "features.verify.description": "分别表达命令执行成功、界面可观察变化和确定性语义证据，避免将三者压缩成一个模糊的成功标志。",
    "features.recovery.title": "有界恢复机制",
    "features.recovery.description": "连续失败拥有明确预算；Tap、Type、Swipe、Back 等非幂等动作不会被运行时盲目重放。",
    "features.trajectory.title": "可审计执行轨迹",
    "features.trajectory.description": "持久化观察、模型响应、动作、执行证据、验证结果、恢复决策、状态迁移和最终结果。",
    "architecture.kicker": "系统架构",
    "architecture.title": "能够确定时走系统路径，必须理解时再使用视觉。",
    "architecture.description": "PhoneAgent 不会把所有操作都交给视觉模型。它将 Android 系统能力与视觉规划闭环结合，并在每一个边界保存可验证证据。",
    "architecture.point1.title": "快速路径",
    "architecture.point1.description": "通过 package/activity 状态解析并启动已安装应用。",
    "architecture.point2.title": "通用路径",
    "architecture.point2.description": "结合截图和任务上下文，规划应用内部的界面导航。",
    "architecture.point3.title": "证据路径",
    "architecture.point3.description": "继续或恢复之前，检查可观察结果或确定性系统状态。",
    "architecture.read": "阅读完整架构说明",
    "quickstart.kicker": "快速开始",
    "quickstart.title": "从克隆仓库到运行第一个任务。",
    "quickstart.description": "不需要前端构建、不依赖工作流框架，也不要求特定厂商的 Accessibility Tree。",
    "quickstart.step1.title": "准备运行环境",
    "quickstart.step1.description": "Linux、Python 3.12+、Android Platform Tools，以及开启 USB 调试的 Android 真机。",
    "quickstart.step2.title": "配置视觉模型",
    "quickstart.step2.description": "接入兼容 OpenAI Chat Completions API 的视觉语言模型服务。",
    "quickstart.step3.title": "执行自然语言任务",
    "quickstart.step3.description": "先验证确定性应用启动，再尝试需要视觉交互的多步骤任务。",
    "quickstart.copy": "复制",
    "quickstart.copied": "已复制",
    "quickstart.result": "运行时已启动 · 设备已连接 · 任务已初始化",
    "trajectory.kicker": "执行可追溯",
    "trajectory.title": "每一次决策都会留下证据。",
    "trajectory.description": "一次运行不只是终端输出。PhoneAgent 会记录状态机、模型交互、结构化动作、执行结果、验证证据、恢复策略以及最终状态。",
    "trajectory.item1": "不只依赖截图，也能完整还原失败运行。",
    "trajectory.item2": "统计模型延迟、Token、动作频率和恢复行为。",
    "trajectory.item3": "构建可复现评估以及后续经验学习数据管线。",
    "trajectory.release": "阅读 v0.1.0 发布说明",
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
    "roadmap.item4.title": "语义验证",
    "roadmap.item4.description": "面向子目标的证据和独立任务评审。",
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
    "limitations.title": "如实表达 v0.1.0 能够证明什么。",
    "limitations.description": "PhoneAgent 当前是 Alpha 阶段的研究与工程运行时。它会显式暴露不确定性，而不是把弱证据包装成确定结论。",
    "limitations.item1.title": "画面变化不等于语义正确",
    "limitations.item1.description": "对于坐标动作，界面发生变化不能证明模型选择了语义上正确的目标。",
    "limitations.item2.title": "任务完成由规划模型报告",
    "limitations.item2.description": "目前由模型通过 finish(...) 报告完整任务结束，尚未引入独立任务评审器。",
    "limitations.item3.title": "受保护页面需要人工接管",
    "limitations.item3.description": "DRM、FLAG_SECURE、密码、验证码和支付流程可能不可观察或属于敏感操作。",
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
  release: `${repositoryUrl}/releases/tag/v0.1.0`,
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
    writeStoredLanguage(language);
  } catch {
    // Storage can be unavailable in hardened browser contexts. The page still works.
  }
}

let currentLanguage = readStoredLanguage() || SITE_CONFIG.defaultLanguage;
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
setupRevealAnimations();
setupCopyButtons();
setupCurrentYear();
