import { CalcError, Calculator, formatNumber } from "./core.js";

const THEME_KEY = "scicalc-theme";
const ANGLE_KEY = "scicalc-angle";
const HISTORY_KEY = "scicalc-history-v1";
const MAX_HISTORY = 30;
const OPERATORS = new Set(["+", "-", "*", "/", "%", "^"]);
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const elements = {
  root: document.documentElement,
  form: document.getElementById("expressionForm"),
  input: document.getElementById("expression"),
  result: document.getElementById("result"),
  lastCommand: document.getElementById("lastCommand"),
  console: document.getElementById("console"),
  consoleStatus: document.getElementById("consoleStatus"),
  statusText: document.getElementById("statusText"),
  errorLine: document.getElementById("errorLine"),
  angleMeta: document.getElementById("angleMeta"),
  angleButtons: Array.from(document.querySelectorAll("[data-angle]")),
  themeToggle: document.getElementById("themeToggle"),
  themeMeta: document.querySelector('meta[name="theme-color"]'),
  copyButton: document.getElementById("copyButton"),
  helpButton: document.getElementById("helpButton"),
  helpDialog: document.getElementById("helpDialog"),
  closeHelp: document.getElementById("closeHelp"),
  historyToggle: document.getElementById("historyToggle"),
  sidePanel: document.getElementById("sidePanel"),
  historyList: document.getElementById("historyList"),
  clearHistory: document.getElementById("clearHistory"),
  clearSession: document.getElementById("clearSession"),
  variableList: document.getElementById("variableList"),
  toast: document.getElementById("toast")
};

function readStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    /* The calculator still works without persistence. */
  }
}

function loadAngleMode() {
  return readStorage(ANGLE_KEY) === "deg" ? "deg" : "rad";
}

function loadHistory() {
  const raw = readStorage(HISTORY_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (entry) =>
          entry &&
          typeof entry.expression === "string" &&
          typeof entry.text === "string" &&
          Number.isFinite(entry.timestamp)
      )
      .slice(0, MAX_HISTORY);
  } catch (error) {
    return [];
  }
}

const calculator = new Calculator({
  angleMode: loadAngleMode(),
  precision: 12
});

let history = loadHistory();
let currentResultText = "0";
let currentResultValue = null;
let historyCursor = -1;
let draftInput = "";
let toastTimer = 0;
let isComposing = false;

function saveHistory() {
  writeStorage(HISTORY_KEY, JSON.stringify(history.slice(0, MAX_HISTORY)));
}

function setStatus(state, label) {
  elements.consoleStatus.dataset.state = state;
  elements.statusText.textContent = label;
}

function setLastCommand(text, idle = false) {
  elements.lastCommand.textContent = text;
  elements.lastCommand.classList.toggle("is-idle", idle);
}

function resultSize(text) {
  const length = String(text).length;
  if (length <= 8) return "lg";
  if (length <= 12) return "md";
  if (length <= 18) return "sm";
  return "xs";
}

function displayResult(text, { animate = true } = {}) {
  currentResultText = text;
  elements.result.textContent = text;
  elements.result.dataset.size = resultSize(text);
  elements.result.classList.remove("is-error");
  elements.copyButton.disabled = false;

  if (animate && !REDUCED_MOTION) {
    elements.result.classList.remove("is-fresh");
    void elements.result.offsetWidth;
    elements.result.classList.add("is-fresh");
  }
}

function clearError() {
  elements.console.classList.remove("is-error");
  elements.errorLine.hidden = true;
  elements.errorLine.textContent = "";
  elements.input.removeAttribute("aria-invalid");
  if (currentResultValue !== null) elements.copyButton.disabled = false;
}

function showError(error, source) {
  const position = Number.isInteger(error.position) ? ` · 第 ${error.position + 1} 列` : "";
  elements.errorLine.textContent = `${error.message}${position}`;
  elements.errorLine.hidden = false;
  elements.console.classList.remove("is-error");
  void elements.console.offsetWidth;
  elements.console.classList.add("is-error");
  elements.input.setAttribute("aria-invalid", "true");
  elements.copyButton.disabled = true;
  setStatus("error", "ERROR");
  setLastCommand(`> ${source}`);

  if (Number.isInteger(error.position)) {
    const positionIndex = Math.min(Math.max(0, error.position), elements.input.value.length);
    elements.input.focus({ preventScroll: true });
    elements.input.setSelectionRange(positionIndex, positionIndex);
  }
}

function setAngleMode(mode, { persist = true } = {}) {
  calculator.setAngleMode(mode);
  elements.angleMeta.textContent = mode.toUpperCase();

  for (const button of elements.angleButtons) {
    const active = button.dataset.angle === mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }

  if (persist) writeStorage(ANGLE_KEY, mode);
}

function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  elements.root.dataset.theme = nextTheme;
  elements.themeMeta.setAttribute("content", nextTheme === "light" ? "#eef0e3" : "#080b09");
  elements.themeToggle.setAttribute(
    "aria-label",
    nextTheme === "dark" ? "切换到浅色模式" : "切换到深色模式"
  );
  elements.themeToggle.title = nextTheme === "dark" ? "切换到浅色模式" : "切换到深色模式";
  writeStorage(THEME_KEY, nextTheme);
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).format(date);
  } catch (error) {
    return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  }
}

function createHistoryEmpty() {
  const empty = document.createElement("div");
  empty.className = "history-empty";
  empty.innerHTML =
    '<span class="history-empty-icon">' +
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.2"></path>' +
    '<path d="M3.5 3.8v4.4h4.4M12 7.5V12l3.1 1.8"></path>' +
    "</svg></span>" +
    "<p>还没有计算记录<span>提交一条表达式后会保存在这里</span></p>";
  return empty;
}

function renderHistory() {
  elements.clearHistory.disabled = history.length === 0;
  elements.historyList.replaceChildren();

  if (history.length === 0) {
    elements.historyList.append(createHistoryEmpty());
    return;
  }

  const fragment = document.createDocumentFragment();
  history.forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.dataset.index = String(index);
    button.title = "载入这条表达式";

    const top = document.createElement("span");
    top.className = "history-item-top";

    const expression = document.createElement("span");
    expression.className = "history-expression";
    expression.textContent = `${entry.expression} =`;

    const time = document.createElement("span");
    time.className = "history-time";
    time.textContent = formatTime(entry.timestamp);

    const value = document.createElement("span");
    value.className = "history-result";
    value.textContent = entry.text;

    top.append(expression, time);
    button.append(top, value);
    fragment.append(button);
  });

  elements.historyList.append(fragment);
}

function renderVariables() {
  elements.variableList.replaceChildren();

  const names = Object.keys(calculator.variables).sort((a, b) => a.localeCompare(b, "zh-CN"));
  const entries = [
    ["ans", formatNumber(calculator.ans, calculator.precision)],
    ...names.map((name) => [name, formatNumber(calculator.variables[name], calculator.precision)])
  ];

  for (const [name, value] of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "variable-chip";
    button.dataset.variable = name;
    button.title = `插入 ${name}`;

    const label = document.createElement("strong");
    label.textContent = name;

    const result = document.createElement("span");
    result.textContent = value;

    button.append(label, result);
    elements.variableList.append(button);
  }

  if (names.length === 0) {
    const empty = document.createElement("span");
    empty.className = "variable-empty";
    empty.textContent = "使用 x = 2^10 保存变量";
    elements.variableList.append(empty);
  }
}

function addHistory(expression, text) {
  history.unshift({
    expression,
    text,
    timestamp: Date.now()
  });
  history = history.slice(0, MAX_HISTORY);
  saveHistory();
  renderHistory();
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("is-visible");
  }, 1700);
}

function resetConsole() {
  elements.input.value = "";
  elements.input.removeAttribute("aria-invalid");
  historyCursor = -1;
  draftInput = "";
  clearError();
  currentResultValue = null;
  currentResultText = "0";
  elements.result.textContent = "0";
  elements.result.dataset.size = "lg";
  elements.result.classList.remove("is-error", "is-fresh");
  elements.copyButton.disabled = false;
  setLastCommand("输入表达式开始计算", true);
  setStatus("ready", "READY");
  elements.input.focus({ preventScroll: true });
}

function runExpression(source) {
  const expression = String(source ?? elements.input.value).trim();
  if (!expression) {
    elements.input.focus({ preventScroll: true });
    return;
  }

  try {
    const result = calculator.evaluate(expression);
    clearError();
    displayResult(result.text);
    currentResultValue = result.value;
    setLastCommand(`> ${expression}${result.assignment ? "" : " ="}`);
    setStatus("success", result.assignment ? "SAVED" : "OK");

    addHistory(expression, result.text);
    renderVariables();

    elements.input.value = "";
    elements.input.removeAttribute("aria-invalid");
    elements.input.focus({ preventScroll: true });
    historyCursor = -1;
    draftInput = "";
  } catch (error) {
    if (error instanceof CalcError) {
      showError(error, expression);
      return;
    }
    throw error;
  }
}

function updateStatusFromInput() {
  const hasInput = elements.input.value.trim().length > 0;
  if (hasInput) {
    setStatus("editing", "EDITING");
  } else if (!elements.console.classList.contains("is-error")) {
    setStatus("ready", "READY");
  }
}

function handleInputChange() {
  if (!elements.errorLine.hidden) clearError();
  historyCursor = -1;
  draftInput = "";
  updateStatusFromInput();
}

function currentSelection() {
  const start = elements.input.selectionStart ?? elements.input.value.length;
  const end = elements.input.selectionEnd ?? start;
  return { start, end };
}

function insertText(text, { caretBack = 0, prefixAns = false } = {}) {
  const input = elements.input;
  const { start, end } = currentSelection();
  const empty = input.value.trim() === "";
  const insertion = prefixAns && empty ? `ans ${text}` : text;

  input.setRangeText(insertion, start, end, "end");
  const caret = start + insertion.length - caretBack;
  input.setSelectionRange(caret, caret);
  input.focus({ preventScroll: true });
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertFunction(name) {
  const input = elements.input;
  const { start, end } = currentSelection();
  const selected = input.value.slice(start, end);

  if (selected) {
    input.setRangeText(`${name}(${selected})`, start, end, "end");
    const caret = start + name.length + selected.length + 2;
    input.setSelectionRange(caret, caret);
  } else {
    input.setRangeText(`${name}()`, start, end, "end");
    const caret = start + name.length + 1;
    input.setSelectionRange(caret, caret);
  }

  input.focus({ preventScroll: true });
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertDecimal() {
  const { start, end } = currentSelection();
  const prefix = elements.input.value.trim() === "" && start === end ? "0." : ".";
  insertText(prefix);
}

function squareSelection() {
  const input = elements.input;
  const { start, end } = currentSelection();
  const selected = input.value.slice(start, end);

  if (selected) {
    insertText(`(${selected})^2`);
  } else if (input.value.trim() === "") {
    insertText("ans^2");
  } else {
    insertText("^2");
  }
}

function backspace() {
  const input = elements.input;
  const { start, end } = currentSelection();

  if (start !== end) {
    input.setRangeText("", start, end, "end");
  } else if (start > 0) {
    input.setRangeText("", start - 1, start, "end");
  } else {
    return;
  }

  input.focus({ preventScroll: true });
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function browseHistory(direction) {
  if (history.length === 0) return;

  if (direction === "up") {
    if (historyCursor === -1) {
      draftInput = elements.input.value;
      historyCursor = 0;
    } else {
      historyCursor = Math.min(historyCursor + 1, history.length - 1);
    }
    elements.input.value = history[historyCursor].expression;
  } else {
    if (historyCursor === -1) return;
    historyCursor -= 1;
    elements.input.value = historyCursor === -1 ? draftInput : history[historyCursor].expression;
  }

  elements.input.focus({ preventScroll: true });
  const end = elements.input.value.length;
  elements.input.setSelectionRange(end, end);
  clearError();
  updateStatusFromInput();
}

function loadExpression(expression) {
  elements.input.value = expression;
  elements.input.focus({ preventScroll: true });
  const end = expression.length;
  elements.input.setSelectionRange(end, end);
  clearError();
  setStatus("editing", "EDITING");
  if (window.matchMedia("(max-width: 900px)").matches) {
    closeHistoryPanel();
  }
}

function openHistoryPanel() {
  elements.sidePanel.classList.add("is-open");
  elements.historyToggle.setAttribute("aria-expanded", "true");
  elements.historyToggle.setAttribute("aria-label", "隐藏历史记录");
  elements.historyList.scrollTop = 0;
}

function closeHistoryPanel() {
  elements.sidePanel.classList.remove("is-open");
  elements.historyToggle.setAttribute("aria-expanded", "false");
  elements.historyToggle.setAttribute("aria-label", "显示历史记录");
}

function toggleHistoryPanel() {
  if (elements.sidePanel.classList.contains("is-open")) {
    closeHistoryPanel();
  } else {
    openHistoryPanel();
  }
}

function openHelp() {
  if (!elements.helpDialog.open) {
    if (typeof elements.helpDialog.showModal === "function") {
      elements.helpDialog.showModal();
    } else {
      elements.helpDialog.setAttribute("open", "");
    }
  }
}

function closeHelp() {
  if (elements.helpDialog.open && typeof elements.helpDialog.close === "function") {
    elements.helpDialog.close();
  } else {
    elements.helpDialog.removeAttribute("open");
  }
}

function copyResult() {
  const text = currentResultText;
  if (!text || elements.copyButton.disabled) return;

  const afterCopy = () => showToast(`已复制 ${text}`);
  const fallback = () => {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    try {
      document.execCommand("copy");
      afterCopy();
    } catch (error) {
      showToast("复制失败，请手动选择结果");
    } finally {
      area.remove();
    }
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(afterCopy).catch(fallback);
  } else {
    fallback();
  }
}

dispatchEventListeners();

function dispatchEventListeners() {
  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (isComposing) return;
    runExpression();
  });

  elements.input.addEventListener("input", handleInputChange);

  elements.input.addEventListener("compositionstart", () => {
    isComposing = true;
  });

  elements.input.addEventListener("compositionend", () => {
    isComposing = false;
  });

  elements.input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;

    if (event.key === "Escape") {
      event.preventDefault();
      resetConsole();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      browseHistory("up");
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      browseHistory("down");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "?" && !event.isComposing && !elements.helpDialog.open) {
      // "?" is not valid in an expression, so it safely doubles as a help
      // shortcut even while the command prompt is focused.
      event.preventDefault();
      openHelp();
    }
  });

  document.querySelector(".keypad").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action], button[data-insert]");
    if (!button) return;

    const action = button.dataset.action;
    if (action === "clear") {
      resetConsole();
    } else if (action === "backspace") {
      backspace();
    } else if (action === "decimal") {
      insertDecimal();
    } else if (action === "equals") {
      runExpression();
    } else if (action === "square") {
      squareSelection();
    } else if (button.dataset.insert !== undefined) {
      const insertion = button.dataset.insert;
      insertText(insertion, { prefixAns: OPERATORS.has(insertion) });
    }

    elements.input.focus({ preventScroll: true });
  });

  document.querySelector(".sci-grid").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-function], button[data-insert]");
    if (!button) return;

    if (button.dataset.function) {
      insertFunction(button.dataset.function);
    } else {
      const insertion = button.dataset.insert;
      const caretBack = Number(button.dataset.caretBack ?? 0);
      insertText(insertion, {
        caretBack: Number.isFinite(caretBack) ? caretBack : 0,
        prefixAns: OPERATORS.has(insertion)
      });
    }
    elements.input.focus({ preventScroll: true });
  });

  document.querySelector(".examples").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-example]");
    if (!button) return;
    elements.input.value = button.dataset.example;
    runExpression(button.dataset.example);
  });

  elements.angleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setAngleMode(button.dataset.angle);
      elements.input.focus({ preventScroll: true });
    });
  });

  elements.themeToggle.addEventListener("click", () => {
    const next = elements.root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
  });

  elements.copyButton.addEventListener("click", copyResult);
  elements.helpButton.addEventListener("click", openHelp);
  elements.closeHelp.addEventListener("click", closeHelp);

  elements.helpDialog.addEventListener("click", (event) => {
    if (event.target === elements.helpDialog) closeHelp();
  });

  elements.historyToggle.addEventListener("click", toggleHistoryPanel);

  elements.historyList.addEventListener("click", (event) => {
    const item = event.target.closest(".history-item");
    if (!item) return;
    const entry = history[Number(item.dataset.index)];
    if (!entry) return;
    loadExpression(entry.expression);
  });

  elements.clearHistory.addEventListener("click", () => {
    history = [];
    saveHistory();
    renderHistory();
    showToast("历史记录已清空");
  });

  if (elements.clearSession) {
    elements.clearSession.addEventListener("click", () => {
      calculator.clear();
      renderVariables();
      showToast("会话变量已重置");
      elements.input.focus({ preventScroll: true });
    });
  }

  elements.variableList.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-variable]");
    if (!chip) return;
    insertText(chip.dataset.variable);
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) {
      elements.sidePanel.classList.remove("is-open");
      elements.historyToggle.setAttribute("aria-expanded", "false");
      elements.historyToggle.setAttribute("aria-label", "显示历史记录");
    }
  });
}

applyTheme(elements.root.dataset.theme === "light" ? "light" : "dark");
setAngleMode(calculator.angleMode);
renderVariables();
renderHistory();
setStatus("ready", "READY");
setLastCommand("输入表达式开始计算", true);
elements.result.dataset.size = "lg";
elements.copyButton.disabled = false;

if (window.matchMedia("(pointer: fine)").matches && window.innerWidth > 900) {
  window.setTimeout(() => {
    elements.input.focus({ preventScroll: true });
  }, 220);
}
