const statusOutput = document.querySelector("#status");
const navigationForm = document.querySelector("#navigation");
const urlInput = document.querySelector("#target-url");
const startButton = document.querySelector("#start");
const stopButton = document.querySelector("#stop");
const reconnectButton = document.querySelector("#reconnect");
const canvas = document.querySelector("#viewport");
const viewportShell = canvas.parentElement;
const hoverHighlight = document.querySelector("#hover-highlight");
const hoverTooltip = document.querySelector("#hover-tooltip");
const hoverLocator = document.querySelector("#hover-locator");
const selectOverlay = document.querySelector("#select-overlay");
const placeholder = document.querySelector("#viewport-placeholder");
const codeOutput = document.querySelector("#code");
document.querySelector('#save-spec').addEventListener('click', () => {
  if (!codeOutput.value.trim()) return;
  const link = document.createElement('a');
  const url = URL.createObjectURL(new Blob([codeOutput.value], { type: 'text/plain;charset=utf-8' }));
  link.href = url; link.download = 'teste-gravado.spec.ts';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
const copyButton = document.querySelector("#copy");
const clearButton = document.querySelector("#clear");
const runButton = document.querySelector("#run");
const copyStatus = document.querySelector("#copy-status");
const stepsOutput = document.querySelector("#steps");
const drawing = canvas.getContext("2d");
const frame = new Image();

let socket;
let sessionStatus = "idle";
let frameCount = 0;
let activeHover;
let activeSelect;
let executionAcknowledged = false;

frame.addEventListener("load", () => {
  drawing.drawImage(frame, 0, 0, canvas.width, canvas.height);
  frameCount++;
  canvas.dataset.frameCount = String(frameCount);
  placeholder.hidden = true;
});

function connect() {
  if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
  setStatus("Conectando…", "starting");
  socket = new WebSocket(`ws://${location.host}/ws`);
  socket.addEventListener("open", updateControls);
  socket.addEventListener("message", ({ data }) => {
    let message;
    try {
      message = JSON.parse(data);
    } catch {
      setStatus("Resposta inválida do servidor.", "error");
      return;
    }
    receive(message);
  });
  socket.addEventListener("close", () => {
    sessionStatus = "idle";
    hideHoverOverlay(false);
    closeSelectOverlay(false);
    setStatus("Desconectado.", "error");
    canvas.setAttribute("aria-disabled", "true");
    updateControls();
  });
  socket.addEventListener("error", () => setStatus("Falha na conexão local.", "error"));
  updateControls();
}

function receive(message) {
  switch (message.type) {
    case "session.state":
      sessionStatus = message.status;
      if (message.url) urlInput.value = message.url;
      setStatus(statusLabel(message.status), message.status);
      canvas.setAttribute("aria-disabled", String(message.status !== "ready"));
      if (message.status !== "ready") {
        hideHoverOverlay(false);
        closeSelectOverlay(false);
      }
      updateControls();
      break;
    case "page.frame":
      frame.src = `data:image/jpeg;base64,${message.jpegBase64}`;
      break;
    case "page.url":
      if (message.url?.startsWith("http://") || message.url?.startsWith("https://")) urlInput.value = message.url;
      break;
    case "page.hover":
      showHoverOverlay(message);
      break;
    case "page.hover.clear":
      hideHoverOverlay(false);
      break;
    case "page.select":
      openSelectOverlay(message);
      break;
    case "page.select.close":
      if (activeSelect?.selectId === message.selectId) closeSelectOverlay(false);
      break;
    case "recording.code":
      codeOutput.value = message.code;
      stepsOutput.value = message.steps;
      updateControls();
      break;
    case "script.done":
      setCopyStatus("Etapas executadas.");
      break;
    case "error":
      setStatus(message.message || "Erro local.", "error");
      break;
  }
}

navigationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!navigationForm.reportValidity()) return;
  send({ type: "session.start", url: urlInput.value });
});

stopButton.addEventListener("click", () => send({ type: "session.stop" }));
clearButton.addEventListener("click", () => send({ type: "recording.clear" }));
reconnectButton.addEventListener("click", connect);
runButton.addEventListener("click", async () => {
  if (!executionAcknowledged) {
    executionAcknowledged = await TestaizeConfirm.ask({ title: 'Rodar etapas editáveis?',
      message: 'As etapas serão executadas na sessão local atual. O código pode navegar e executar comandos Playwright.',
      confirmLabel: 'Rodar etapas' });
  }
  if (executionAcknowledged && stepsOutput.value.trim()) send({ type: "script.run", steps: stepsOutput.value });
});
stepsOutput.addEventListener("input", updateControls);

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(codeOutput.value);
    setCopyStatus("Código copiado.");
  } catch {
    codeOutput.focus();
    codeOutput.select();
    setCopyStatus("Código selecionado. Use Ctrl+C para copiar.");
  }
});

canvas.addEventListener("pointerdown", (event) => {
  if (!ready()) return;
  event.preventDefault();
  canvas.focus();
  canvas.setPointerCapture(event.pointerId);
  sendPointer("down", event);
});
canvas.addEventListener("pointermove", (event) => {
  if (ready()) sendPointer("move", event);
});
canvas.addEventListener("pointerleave", () => hideHoverOverlay(true));
canvas.addEventListener("pointerup", (event) => {
  if (!ready()) return;
  event.preventDefault();
  sendPointer("up", event);
  if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());
canvas.addEventListener(
  "wheel",
  (event) => {
    if (!ready()) return;
    event.preventDefault();
    send({ type: "input.wheel", deltaX: clamp(event.deltaX, -10_000, 10_000), deltaY: clamp(event.deltaY, -10_000, 10_000) });
  },
  { passive: false },
);
canvas.addEventListener("keydown", (event) => {
  if (!ready() || event.key === "Tab") return;
  event.preventDefault();
  send({
    type: "input.key",
    phase: "down",
    key: event.key,
    ...(event.code ? { code: event.code } : {}),
    modifiers: modifiers(event),
  });
});
canvas.addEventListener("keyup", (event) => {
  if (!ready() || event.key === "Tab") return;
  event.preventDefault();
  send({
    type: "input.key",
    phase: "up",
    key: event.key,
    ...(event.code ? { code: event.code } : {}),
    modifiers: modifiers(event),
  });
});
canvas.addEventListener("paste", (event) => {
  if (!ready()) return;
  const text = event.clipboardData?.getData("text") ?? "";
  if (!text) return;
  event.preventDefault();
  send({ type: "input.text", text: text.slice(0, 32 * 1024) });
});

selectOverlay.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    closeSelectOverlay(true);
    canvas.focus();
    return;
  }
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const options = [...selectOverlay.querySelectorAll(".select-option:not(:disabled)")];
  if (!options.length) return;
  event.preventDefault();
  const current = options.indexOf(document.activeElement);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? options.length - 1
        : (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
  options[next].focus();
});

document.addEventListener(
  "pointerdown",
  (event) => {
    if (activeSelect && !selectOverlay.contains(event.target)) closeSelectOverlay(true);
  },
  true,
);
window.addEventListener("resize", () => {
  positionHoverOverlay();
  positionSelectOverlay();
});

function showHoverOverlay(message) {
  if (activeSelect || !message.rect || typeof message.locator !== "string") return;
  activeHover = { rect: message.rect, locator: message.locator };
  hoverLocator.textContent = message.locator;
  hoverTooltip.title = message.locator;
  hoverHighlight.hidden = false;
  hoverTooltip.hidden = false;
  positionHoverOverlay();
}

function hideHoverOverlay(notify) {
  const hadHover = Boolean(activeHover);
  activeHover = undefined;
  hoverHighlight.hidden = true;
  hoverTooltip.hidden = true;
  hoverLocator.textContent = "";
  if (notify && hadHover && ready()) send({ type: "input.hover.clear" });
}

function positionHoverOverlay() {
  if (!activeHover || hoverHighlight.hidden) return;
  const { x, y, width, height } = activeHover.rect;
  const scaleX = viewportShell.clientWidth / canvas.width;
  const scaleY = viewportShell.clientHeight / canvas.height;
  const gap = 6;
  const left = x * scaleX;
  const top = y * scaleY;
  hoverHighlight.style.left = `${left}px`;
  hoverHighlight.style.top = `${top}px`;
  hoverHighlight.style.width = `${width * scaleX}px`;
  hoverHighlight.style.height = `${height * scaleY}px`;

  hoverTooltip.style.left = "0";
  hoverTooltip.style.top = "0";
  hoverTooltip.style.transform = "none";
  const tooltipLeft = clamp(left, gap, viewportShell.clientWidth - hoverTooltip.offsetWidth - gap);
  let tooltipTop = top + height * scaleY + gap;
  if (tooltipTop + hoverTooltip.offsetHeight > viewportShell.clientHeight - gap) {
    tooltipTop = top - gap;
    hoverTooltip.style.transform = "translateY(-100%)";
  }
  hoverTooltip.style.left = `${tooltipLeft}px`;
  hoverTooltip.style.top = `${tooltipTop}px`;
}

function openSelectOverlay(message) {
  if (!Array.isArray(message.options) || !message.options.length) return;
  hideHoverOverlay(false);
  closeSelectOverlay(false);
  activeSelect = { selectId: message.selectId, rect: message.rect };
  const buttons = message.options.map((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "select-option";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(Boolean(option.selected)));
    button.disabled = Boolean(option.disabled);
    button.dataset.index = String(option.index);
    button.textContent = option.label || `Opção ${option.index + 1}`;
    button.addEventListener("click", () => {
      send({ type: "input.select", selectId: message.selectId, index: option.index });
      closeSelectOverlay(false);
      canvas.focus();
    });
    return button;
  });
  selectOverlay.replaceChildren(...buttons);
  selectOverlay.hidden = false;
  positionSelectOverlay();
  requestAnimationFrame(() => {
    const selected = selectOverlay.querySelector('[aria-selected="true"]:not(:disabled)');
    const first = selectOverlay.querySelector(".select-option:not(:disabled)");
    (selected || first)?.focus({ preventScroll: true });
    selected?.scrollIntoView({ block: "nearest" });
  });
}

function closeSelectOverlay(cancel) {
  const select = activeSelect;
  activeSelect = undefined;
  selectOverlay.hidden = true;
  selectOverlay.replaceChildren();
  if (cancel && select && ready()) send({ type: "input.select", selectId: select.selectId, index: null });
}

function positionSelectOverlay() {
  if (!activeSelect || selectOverlay.hidden) return;
  const { x, y, width, height } = activeSelect.rect;
  const scaleX = viewportShell.clientWidth / canvas.width;
  const scaleY = viewportShell.clientHeight / canvas.height;
  const gap = 6;
  const popupWidth = Math.min(Math.max(width * scaleX, 220), viewportShell.clientWidth - gap * 2);
  const left = clamp(x * scaleX, gap, viewportShell.clientWidth - popupWidth - gap);
  let top = (y + height) * scaleY + gap;
  selectOverlay.style.width = `${popupWidth}px`;
  selectOverlay.style.left = `${left}px`;
  selectOverlay.style.top = `${top}px`;
  selectOverlay.style.transform = "none";
  if (top + selectOverlay.offsetHeight > viewportShell.clientHeight - gap) {
    top = y * scaleY - gap;
    selectOverlay.style.top = `${top}px`;
    selectOverlay.style.transform = "translateY(-100%)";
  }
}

function sendPointer(phase, event) {
  const rect = canvas.getBoundingClientRect();
  const x = clamp(((event.clientX - rect.left) / rect.width) * canvas.width, 0, canvas.width);
  const y = clamp(((event.clientY - rect.top) / rect.height) * canvas.height, 0, canvas.height);
  send({
    type: "input.pointer",
    phase,
    x,
    y,
    button: ["left", "middle", "right"][event.button] ?? "left",
    clickCount: clamp(event.detail || 1, 1, 3),
  });
}

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function ready() {
  return socket?.readyState === WebSocket.OPEN && sessionStatus === "ready";
}

function modifiers(event) {
  return [
    event.altKey && "Alt",
    event.ctrlKey && "Control",
    event.metaKey && "Meta",
    event.shiftKey && "Shift",
  ].filter(Boolean);
}

function updateControls() {
  const connected = socket?.readyState === WebSocket.OPEN;
  const busy = sessionStatus === "starting" || sessionStatus === "stopping";
  startButton.disabled = !connected || busy;
  stopButton.disabled = !connected || sessionStatus === "idle" || sessionStatus === "stopping";
  clearButton.disabled = !ready();
  copyButton.disabled = !codeOutput.value;
  runButton.disabled = !ready() || !stepsOutput.value.trim();
  reconnectButton.hidden = socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING;
}

function setStatus(text, status) {
  statusOutput.value = text;
  statusOutput.dataset.status = status;
}

function setCopyStatus(text) {
  copyStatus.value = text;
  copyStatus.textContent = text;
}

function statusLabel(status) {
  return {
    idle: "Ocioso",
    starting: "Iniciando Chromium…",
    ready: "Pronto",
    stopping: "Encerrando…",
    error: "Erro",
  }[status] ?? "Estado desconhecido";
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

updateControls();
connect();
