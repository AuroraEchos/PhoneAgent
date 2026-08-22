"use strict";

const GUIDE_REPOSITORY = "https://github.com/AuroraEchos/PhoneAgent";

const GUIDE_DOCUMENTS = [
  { key: "overview", file: "README.md", title: "子系统总览", short: "总览", number: "00" },
  { key: "entry", file: "ENTRY_AND_CONFIGURATION_SUBSYSTEM.md", title: "入口与配置", short: "入口与配置", number: "01" },
  { key: "device", file: "DEVICE_AND_OBSERVATION_SUBSYSTEM.md", title: "设备与观测", short: "设备与观测", number: "02" },
  { key: "model", file: "MODEL_AND_CONTEXT_SUBSYSTEM.md", title: "模型与上下文", short: "模型与上下文", number: "03" },
  { key: "agent", file: "AGENT_RUNTIME_AND_STATE_SUBSYSTEM.md", title: "Agent 编排与状态", short: "Agent 编排", number: "04" },
  { key: "action", file: "ACTION_SUBSYSTEM.md", title: "动作子系统", short: "动作子系统", number: "05" },
  { key: "semantic", file: "SEMANTIC_REVIEW_SUBSYSTEM.md", title: "语义复核", short: "语义复核", number: "06" },
  { key: "freshness", file: "FRESHNESS_SUBSYSTEM.md", title: "执行前新鲜度", short: "执行前新鲜度", number: "07" },
  { key: "verification", file: "VERIFICATION_SUBSYSTEM.md", title: "动作效果验证", short: "动作效果验证", number: "08" },
  { key: "recovery", file: "RECOVERY_SUBSYSTEM.md", title: "失败恢复", short: "失败恢复", number: "09" },
  { key: "observability", file: "OBSERVABILITY_AND_EVALUATION_SUBSYSTEM.md", title: "可观测性与评估", short: "可观测性", number: "10" },
  { key: "web", file: "WEB_CONSOLE_SUBSYSTEM.md", title: "本地 Web 控制台", short: "Web 控制台", number: "11" },
];

const documentByKey = new Map(GUIDE_DOCUMENTS.map((item) => [item.key, item]));
const documentByFile = new Map(GUIDE_DOCUMENTS.map((item) => [item.file.toLowerCase(), item]));
const contentElement = document.querySelector("[data-doc-content]");
const tocElement = document.querySelector("[data-doc-toc]");
const pagerElement = document.querySelector("[data-doc-pager]");
const sourceElement = document.querySelector("[data-guide-source]");
const sidebarElement = document.querySelector("[data-docs-sidebar]");
const sidebarToggle = document.querySelector("[data-docs-nav-toggle]");
let activeDocumentKey = null;
let headingObserver = null;
let requestSequence = 0;

function selectedDocumentFromUrl() {
  const key = new URLSearchParams(window.location.search).get("doc") || "overview";
  return documentByKey.has(key) ? key : "overview";
}

function makeElement(tag, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  return element;
}

function appendText(parent, text) {
  if (text) parent.append(document.createTextNode(text));
}

function resolveMarkdownLink(target, currentDocument) {
  if (/^(https?:|mailto:)/i.test(target)) {
    return { href: target, external: true };
  }

  if (target.startsWith("#")) {
    return { href: target, external: false };
  }

  const syntheticBase = "https://repository.invalid/docs/subsystems/" + currentDocument.file;
  const resolved = new URL(target, syntheticBase);
  const repositoryPath = resolved.pathname.replace(/^\//, "");
  const fileName = repositoryPath.split("/").pop().toLowerCase();
  const linkedDocument = documentByFile.get(fileName);

  if (linkedDocument) {
    const suffix = resolved.hash || "";
    return {
      href: "guide.html?doc=" + encodeURIComponent(linkedDocument.key) + suffix,
      external: false,
      documentKey: linkedDocument.key,
      hash: suffix,
    };
  }

  const lastSegment = repositoryPath.split("/").pop();
  const isDirectory = !lastSegment.includes(".");
  return {
    href: GUIDE_REPOSITORY + "/" + (isDirectory ? "tree" : "blob") + "/main/" + repositoryPath + (resolved.hash || ""),
    external: true,
  };
}

function appendInline(parent, source, currentDocument) {
  const tokenPattern = /(\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\x60([^\x60]+)\x60|\*([^*]+)\*)/g;
  let cursor = 0;
  let match;

  while ((match = tokenPattern.exec(source)) !== null) {
    appendText(parent, source.slice(cursor, match.index));

    if (match[2] !== undefined) {
      const link = makeElement("a");
      const resolved = resolveMarkdownLink(match[3], currentDocument);
      link.href = resolved.href;
      appendInline(link, match[2], currentDocument);

      if (resolved.external) {
        link.target = "_blank";
        link.rel = "noreferrer";
      }
      if (resolved.documentKey) {
        link.dataset.guideDocument = resolved.documentKey;
        if (resolved.hash) link.dataset.guideHash = resolved.hash;
      }
      parent.append(link);
    } else if (match[4] !== undefined) {
      const strong = makeElement("strong");
      appendInline(strong, match[4], currentDocument);
      parent.append(strong);
    } else if (match[5] !== undefined) {
      const code = makeElement("code");
      code.textContent = match[5];
      parent.append(code);
    } else if (match[6] !== undefined) {
      const emphasis = makeElement("em");
      appendInline(emphasis, match[6], currentDocument);
      parent.append(emphasis);
    }

    cursor = tokenPattern.lastIndex;
  }

  appendText(parent, source.slice(cursor));
}

function splitTableRow(line) {
  let value = line.trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function headingSlug(text, seenSlugs) {
  const base = text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\x60/g, "")
    .replace(/\*\*/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\u4e00-\u9fff]+/gu, "-")
    .replace(/^-+|-+$/g, "") || "section";
  const count = seenSlugs.get(base) || 0;
  seenSlugs.set(base, count + 1);
  return count === 0 ? base : base + "-" + (count + 1);
}

function lineStartsBlock(lines, index) {
  const line = lines[index] || "";
  if (!line.trim()) return true;
  if (/^#{1,6}\s+/.test(line)) return true;
  if (/^\x60\x60\x60/.test(line.trim())) return true;
  if (/^(\s*)([-*+]|\d+\.)\s+/.test(line)) return true;
  if (/^\s*---+\s*$/.test(line)) return true;
  return index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1]);
}

function createCodeBlock(code, language) {
  const wrapper = makeElement("div", "docs-code");
  const toolbar = makeElement("div", "docs-code-toolbar");
  const label = makeElement("span");
  const copyButton = makeElement("button");
  const pre = makeElement("pre");
  const codeElement = makeElement("code");

  label.textContent = language || "text";
  copyButton.type = "button";
  copyButton.textContent = "复制";
  copyButton.setAttribute("aria-label", "复制代码");
  codeElement.textContent = code;
  if (language) codeElement.className = "language-" + language;

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = code;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.append(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    copyButton.textContent = "已复制";
    window.setTimeout(() => { copyButton.textContent = "复制"; }, 1400);
  });

  toolbar.append(label, copyButton);
  pre.append(codeElement);
  wrapper.append(toolbar, pre);
  return wrapper;
}

function renderMarkdown(markdown, currentDocument) {
  const fragment = document.createDocumentFragment();
  const headings = [];
  const seenSlugs = new Map();
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.trim().match(/^\x60\x60\x60\s*([A-Za-z0-9_-]*)\s*$/);
    if (fence) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !/^\x60\x60\x60\s*$/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      fragment.append(createCodeBlock(codeLines.join("\n"), fence[1]));
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const heading = makeElement("h" + level);
      const slug = headingSlug(headingMatch[2], seenSlugs);
      heading.id = slug;
      appendInline(heading, headingMatch[2], currentDocument);

      if (level <= 3) {
        const anchor = makeElement("a", "docs-heading-anchor");
        anchor.href = "#" + slug;
        anchor.setAttribute("aria-label", "链接到本节");
        anchor.textContent = "#";
        heading.append(anchor);
      }
      if (level === 2 || level === 3) {
        headings.push({ id: slug, level, title: heading.textContent.replace(/#$/, "") });
      }

      fragment.append(heading);
      index += 1;
      continue;
    }

    if (index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1])) {
      const wrapper = makeElement("div", "docs-table-wrap");
      const table = makeElement("table");
      const head = makeElement("thead");
      const headRow = makeElement("tr");
      splitTableRow(line).forEach((cell) => {
        const th = makeElement("th");
        appendInline(th, cell, currentDocument);
        headRow.append(th);
      });
      head.append(headRow);
      table.append(head);
      index += 2;

      const body = makeElement("tbody");
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        const row = makeElement("tr");
        splitTableRow(lines[index]).forEach((cell) => {
          const td = makeElement("td");
          appendInline(td, cell, currentDocument);
          row.append(td);
        });
        body.append(row);
        index += 1;
      }
      table.append(body);
      wrapper.append(table);
      fragment.append(wrapper);
      continue;
    }

    const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.+)$/);
    if (listMatch) {
      const ordered = /\d+\./.test(listMatch[2]);
      const list = makeElement(ordered ? "ol" : "ul");

      while (index < lines.length) {
        const itemMatch = lines[index].match(/^(\s*)([-*+]|\d+\.)\s+(.+)$/);
        if (!itemMatch || /\d+\./.test(itemMatch[2]) !== ordered) break;
        const item = makeElement("li");
        appendInline(item, itemMatch[3], currentDocument);
        list.append(item);
        index += 1;
      }
      fragment.append(list);
      continue;
    }

    if (/^\s*---+\s*$/.test(line)) {
      fragment.append(makeElement("hr"));
      index += 1;
      continue;
    }

    const paragraphLines = [line.trim()];
    index += 1;
    while (index < lines.length && !lineStartsBlock(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    const paragraph = makeElement("p");
    appendInline(paragraph, paragraphLines.join(" "), currentDocument);
    fragment.append(paragraph);
  }

  return { fragment, headings };
}

function setActiveDirectory(key) {
  document.querySelectorAll("[data-doc-link]").forEach((link) => {
    const active = link.dataset.docLink === key;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function renderTableOfContents(headings) {
  tocElement.replaceChildren();
  headingObserver?.disconnect();

  headings.forEach((heading) => {
    const link = makeElement("a", heading.level === 3 ? "toc-level-three" : "");
    link.href = "#" + heading.id;
    link.textContent = heading.title;
    link.dataset.tocId = heading.id;
    tocElement.append(link);
  });

  if (!headings.length || !("IntersectionObserver" in window)) return;

  const links = [...tocElement.querySelectorAll("a")];
  const setActive = (id) => {
    links.forEach((link) => link.classList.toggle("active", link.dataset.tocId === id));
  };

  headingObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting);
      if (visible.length) setActive(visible[0].target.id);
    },
    { rootMargin: "-110px 0px -70% 0px", threshold: 0 },
  );

  headings.forEach((heading) => {
    const element = document.getElementById(heading.id);
    if (element) headingObserver.observe(element);
  });
}

function renderPager(currentDocument) {
  const currentIndex = GUIDE_DOCUMENTS.findIndex((item) => item.key === currentDocument.key);
  pagerElement.replaceChildren();

  const addPagerLink = (documentItem, direction) => {
    if (!documentItem) {
      pagerElement.append(makeElement("span", "docs-pager-placeholder"));
      return;
    }
    const link = makeElement("a", "docs-pager-link docs-pager-" + direction);
    link.href = "guide.html?doc=" + encodeURIComponent(documentItem.key);
    link.dataset.guideDocument = documentItem.key;
    const label = makeElement("small");
    const title = makeElement("strong");
    label.textContent = direction === "previous" ? "上一篇" : "下一篇";
    title.textContent = documentItem.number + " · " + documentItem.short;
    link.append(label, title);
    pagerElement.append(link);
  };

  addPagerLink(GUIDE_DOCUMENTS[currentIndex - 1], "previous");
  addPagerLink(GUIDE_DOCUMENTS[currentIndex + 1], "next");
}

function updateSourceLink(currentDocument) {
  sourceElement.href = GUIDE_REPOSITORY + "/blob/main/docs/subsystems/" + currentDocument.file;
}

function closeDirectory() {
  sidebarElement?.classList.remove("open");
  sidebarToggle?.setAttribute("aria-expanded", "false");
}

async function loadDocument(key, options) {
  const config = options || {};
  const currentDocument = documentByKey.get(key) || documentByKey.get("overview");
  const requestId = ++requestSequence;
  activeDocumentKey = currentDocument.key;
  setActiveDirectory(currentDocument.key);
  updateSourceLink(currentDocument);
  closeDirectory();

  if (config.updateHistory) {
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("doc", currentDocument.key);
    nextUrl.hash = config.hash || "";
    window.history.pushState({ doc: currentDocument.key }, "", nextUrl);
  }

  const loading = makeElement("div", "docs-loading");
  loading.append(makeElement("span"));
  const loadingText = makeElement("p");
  loadingText.textContent = "正在加载 " + currentDocument.title + "……";
  loading.append(loadingText);
  contentElement.replaceChildren(loading);
  tocElement.replaceChildren();
  pagerElement.replaceChildren();

  try {
    const response = await fetch("subsystems/" + currentDocument.file, { cache: "no-cache" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const markdown = await response.text();
    if (requestId !== requestSequence) return;

    const rendered = renderMarkdown(markdown, currentDocument);
    contentElement.replaceChildren(rendered.fragment);
    renderTableOfContents(rendered.headings);
    renderPager(currentDocument);
    document.title = currentDocument.title + " — PhoneAgent 源码导读";

    const targetHash = config.hash || window.location.hash;
    if (targetHash) {
      window.requestAnimationFrame(() => {
        const target = document.getElementById(decodeURIComponent(targetHash.slice(1)));
        target?.scrollIntoView({ block: "start" });
      });
    } else if (config.scrollToContent) {
      const top = contentElement.getBoundingClientRect().top + window.scrollY - 100;
      window.scrollTo({ top, behavior: "smooth" });
    }
  } catch (error) {
    if (requestId !== requestSequence) return;
    const errorBox = makeElement("div", "docs-error");
    const title = makeElement("h2");
    const description = makeElement("p");
    const sourceLink = makeElement("a", "button button-primary");
    title.textContent = "文档暂时无法加载";
    description.textContent = "请通过本地 HTTP 服务或 GitHub Pages 打开此页面。错误信息：" + error.message;
    sourceLink.href = GUIDE_REPOSITORY + "/blob/main/docs/subsystems/" + currentDocument.file;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    sourceLink.textContent = "在 GitHub 阅读原文";
    errorBox.append(title, description, sourceLink);
    contentElement.replaceChildren(errorBox);
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-guide-document]");
  if (!link) return;
  const key = link.dataset.guideDocument;
  if (!documentByKey.has(key)) return;
  event.preventDefault();
  loadDocument(key, {
    updateHistory: true,
    scrollToContent: true,
    hash: link.dataset.guideHash || "",
  });
});

document.querySelectorAll("[data-doc-link]").forEach((link) => {
  link.dataset.guideDocument = link.dataset.docLink;
});

sidebarToggle?.addEventListener("click", () => {
  const open = sidebarToggle.getAttribute("aria-expanded") === "true";
  sidebarToggle.setAttribute("aria-expanded", String(!open));
  sidebarElement?.classList.toggle("open", !open);
});

window.addEventListener("popstate", () => {
  loadDocument(selectedDocumentFromUrl(), { hash: window.location.hash });
});

loadDocument(selectedDocumentFromUrl(), { hash: window.location.hash });
