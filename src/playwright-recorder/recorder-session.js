import { chromium, expect, } from "./runtime.js";
import { VIEWPORT, } from "./protocol.js";
import { PlaywrightRecorderAdapter, RecorderAdapterError } from "./playwright-recorder-adapter.js";
const NAVIGATION_TIMEOUT_MS = 20_000;
const FRAME_RETRY_MS = 16;
const HOVER_DELAY_MS = 120;
const MAX_SELECT_OPTIONS = 200;
const MAX_SELECT_LABEL_LENGTH = 256;
const SCRIPT_TIMEOUT_MS = 30_000;
export class SessionError extends Error {
    code;
    recoverable;
    constructor(code, message, recoverable) {
        super(message);
        this.name = "SessionError";
        this.code = code;
        this.recoverable = recoverable;
    }
}
export class RecorderSession {
    #send;
    #status = "idle";
    #targetUrl;
    #browser;
    #context;
    #page;
    #cdp;
    #adapter;
    #lifecycle = Promise.resolve();
    #inputQueue = Promise.resolve();
    #generation = 0;
    #closingResources = false;
    #pressedKeys = new Set();
    #pendingSelect;
    #nextSelectId = 0;
    #suppressPointerUp = false;
    #hoverPoint;
    #hoverTimer;
    #hoverVersion = 0;
    #lastHoverKey;
    #latestFrame;
    #frameTimer;
    constructor(send) {
        this.#send = send;
    }
    get status() {
        return this.#status;
    }
    publishState() {
        this.#sendState();
    }
    start(url) {
        return this.#enqueueLifecycle(() => this.#startNow(url));
    }
    close() {
        return this.#enqueueLifecycle(async () => {
            if (!this.#hasResources() && this.#status === "idle")
                return;
            this.#setStatus("stopping");
            await this.#stopResources();
            this.#targetUrl = undefined;
            this.#setStatus("idle");
        });
    }
    clearRecording() {
        if (this.#status !== "ready" || !this.#adapter)
            throw new SessionError("SESSION_NOT_READY", "Sessão ainda não está pronta.", true);
        this.#adapter.clear();
    }
    handleInput(message) {
        if (this.#status !== "ready" || !this.#page)
            return Promise.reject(new SessionError("SESSION_NOT_READY", "Sessão ainda não está pronta.", true));
        const page = this.#page;
        const generation = this.#generation;
        const operation = this.#inputQueue.then(async () => {
            if (generation !== this.#generation || this.#status !== "ready" || page.isClosed())
                throw new SessionError("SESSION_NOT_READY", "Sessão ainda não está pronta.", true);
            try {
                await this.#dispatchInput(page, message);
            }
            catch (error) {
                if (error instanceof SessionError)
                    throw error;
                throw new SessionError("INVALID_MESSAGE", "Entrada não suportada pelo navegador.", true);
            }
        });
        this.#inputQueue = operation.catch(() => { });
        return operation;
    }
    async #startNow(url) {
        if (this.#hasResources()) {
            this.#setStatus("stopping");
            await this.#stopResources();
        }
        this.#targetUrl = url;
        this.#setStatus("starting");
        const generation = ++this.#generation;
        let phase = "browser";
        try {
            const browser = await chromium.launch({ headless: true });
            this.#browser = browser;
            browser.once("disconnected", () => {
                if (generation === this.#generation && !this.#closingResources && this.#status === "ready")
                    this.#failUnexpectedBrowserClose();
            });
            const context = await browser.newContext({ viewport: VIEWPORT });
            this.#context = context;
            const page = await context.newPage();
            this.#page = page;
            page.on("framenavigated", (frame) => {
                if (generation === this.#generation && frame === page.mainFrame()) {
                    this.#clearHover();
                    void this.#closeSelect();
                    this.#send({ type: "page.url", url: frame.url() });
                }
            });
            phase = "recorder";
            const adapter = new PlaywrightRecorderAdapter(context, (code, steps) => this.#send({ type: "recording.code", code, steps }), (error) => this.#failRecorder(error));
            this.#adapter = adapter;
            await adapter.enable();
            phase = "navigation";
            await page.goto(url, { waitUntil: "domcontentloaded", timeout: NAVIGATION_TIMEOUT_MS });
            await adapter.whenIdle();
            phase = "screencast";
            await this.#startScreencast(context, page, generation);
            this.#setStatus("ready");
        }
        catch (error) {
            await this.#stopResources();
            this.#setStatus("error");
            if (error instanceof RecorderAdapterError)
                throw new SessionError("RECORDER_INCOMPATIBLE", error.message, false);
            if (phase === "navigation")
                throw new SessionError("NAVIGATION_FAILED", "Não foi possível abrir o destino.", true);
            throw new SessionError("BROWSER_FAILED", "Chromium não pôde iniciar ou encerrou inesperadamente.", false);
        }
    }
    async #startScreencast(context, page, generation) {
        const cdp = await context.newCDPSession(page);
        this.#cdp = cdp;
        cdp.on("Page.screencastFrame", ({ data, sessionId }) => {
            void cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => { });
            if (generation !== this.#generation)
                return;
            this.#offerFrame({
                type: "page.frame",
                jpegBase64: data,
                width: VIEWPORT.width,
                height: VIEWPORT.height,
            });
        });
        await cdp.send("Page.startScreencast", {
            format: "jpeg",
            quality: 70,
            maxWidth: VIEWPORT.width,
            maxHeight: VIEWPORT.height,
            everyNthFrame: 1,
        });
    }
    #offerFrame(frame) {
        // ponytail: JSON/base64 keeps one local session simple; use binary frames only after measured transport pressure.
        this.#latestFrame = frame;
        this.#flushFrame();
    }
    #flushFrame() {
        if (this.#frameTimer || !this.#latestFrame)
            return;
        const frame = this.#latestFrame;
        this.#latestFrame = undefined;
        if (this.#send(frame) === false) {
            if (!this.#latestFrame)
                this.#latestFrame = frame;
            this.#frameTimer = setTimeout(() => {
                this.#frameTimer = undefined;
                this.#flushFrame();
            }, FRAME_RETRY_MS);
        }
    }
    async #dispatchInput(page, message) {
        switch (message.type) {
            case "input.pointer":
                if (message.phase === "move") {
                    await page.mouse.move(message.x, message.y);
                    this.#scheduleHover(page, message.x, message.y);
                }
                else if (message.phase === "down") {
                    this.#clearHover();
                    if ((message.button ?? "left") === "left" && (await this.#openSelectAt(page, message.x, message.y))) {
                        this.#suppressPointerUp = true;
                        return;
                    }
                    await this.#closeSelect();
                    await page.mouse.down({ button: message.button ?? "left", clickCount: message.clickCount ?? 1 });
                }
                else {
                    if (this.#suppressPointerUp) {
                        this.#suppressPointerUp = false;
                        return;
                    }
                    await page.mouse.up({ button: message.button ?? "left", clickCount: message.clickCount ?? 1 });
                }
                return;
            case "input.wheel":
                this.#clearHover();
                await page.mouse.wheel(message.deltaX, message.deltaY);
                return;
            case "input.hover.clear":
                this.#clearHover();
                return;
            case "input.text":
                await page.keyboard.insertText(message.text);
                return;
            case "script.run":
                await this.#runSteps(page, message.steps);
                return;
            case "input.select":
                await this.#chooseSelect(message.selectId, message.index);
                return;
            case "input.key":
                // Host key values already include CapsLock casing; forwarding the lock fragments recorder fills.
                if (message.key === "CapsLock")
                    return;
                for (const modifier of message.modifiers ?? []) {
                    if (modifier !== message.key && !this.#pressedKeys.has(modifier)) {
                        await page.keyboard.down(modifier);
                        this.#pressedKeys.add(modifier);
                    }
                }
                if (message.phase === "down") {
                    await page.keyboard.down(message.key);
                    this.#pressedKeys.add(message.key);
                }
                else {
                    await page.keyboard.up(message.key);
                    this.#pressedKeys.delete(message.key);
                }
        }
    }
    #scheduleHover(page, x, y) {
        if (this.#status !== "ready" || this.#pendingSelect)
            return;
        const version = ++this.#hoverVersion;
        this.#hoverPoint = { page, x, y, generation: this.#generation, version };
        if (this.#hoverTimer)
            return;
        this.#hoverTimer = setTimeout(() => {
            this.#hoverTimer = undefined;
            const point = this.#hoverPoint;
            this.#hoverPoint = undefined;
            if (point)
                void this.#inspectHover(point);
        }, HOVER_DELAY_MS);
    }
    async #inspectHover(point) {
        if (point.version !== this.#hoverVersion ||
            point.generation !== this.#generation ||
            this.#status !== "ready" ||
            this.#pendingSelect ||
            point.page.isClosed())
            return;
        try {
            const descriptor = await point.page.evaluate(({ x, y }) => {
                const rawTarget = document.elementFromPoint(x, y);
                if (!rawTarget)
                    return null;
                const element = rawTarget.closest("a,button,input,select,textarea,[role],[data-testid]") ?? rawTarget;
                const rect = element.getBoundingClientRect();
                if (![rect.x, rect.y, rect.width, rect.height].every(Number.isFinite))
                    return null;
                const clippedRect = {
                    x: Math.max(0, rect.left),
                    y: Math.max(0, rect.top),
                    width: Math.min(innerWidth, rect.right) - Math.max(0, rect.left),
                    height: Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top),
                };
                if (clippedRect.width < 1 || clippedRect.height < 1)
                    return null;
                const normalize = (value) => (value ?? "").replace(/\s+/g, " ").trim().slice(0, 160);
                const tag = element.tagName.toLowerCase();
                const explicitRole = normalize(element.getAttribute("role")).split(" ")[0] ?? "";
                let role = explicitRole;
                if (!role) {
                    if (tag === "a" && element.hasAttribute("href"))
                        role = "link";
                    else if (tag === "button")
                        role = "button";
                    else if (tag === "textarea")
                        role = "textbox";
                    else if (tag === "select")
                        role = element instanceof HTMLSelectElement && (element.multiple || element.size > 1) ? "listbox" : "combobox";
                    else if (tag === "img")
                        role = "img";
                    else if (/^h[1-6]$/.test(tag))
                        role = "heading";
                    else if (tag === "li")
                        role = "listitem";
                    else if (tag === "ul" || tag === "ol")
                        role = "list";
                    else if (tag === "table")
                        role = "table";
                    else if (tag === "tr")
                        role = "row";
                    else if (tag === "td")
                        role = "cell";
                    else if (tag === "th")
                        role = element.getAttribute("scope") === "row" ? "rowheader" : "columnheader";
                    else if (tag === "nav")
                        role = "navigation";
                    else if (tag === "main")
                        role = "main";
                    else if (tag === "dialog")
                        role = "dialog";
                    else if (tag === "option")
                        role = "option";
                    else if (tag === "input" && element instanceof HTMLInputElement) {
                        const type = element.type.toLowerCase();
                        if (type === "hidden")
                            return null;
                        if (type === "checkbox")
                            role = "checkbox";
                        else if (type === "radio")
                            role = "radio";
                        else if (type === "range")
                            role = "slider";
                        else if (type === "number")
                            role = "spinbutton";
                        else if (type === "search")
                            role = "searchbox";
                        else if (["button", "submit", "reset", "image"].includes(type))
                            role = "button";
                        else if (["email", "tel", "text", "url"].includes(type))
                            role = "textbox";
                    }
                }
                const labelledBy = normalize(element
                    .getAttribute("aria-labelledby")
                    ?.split(/\s+/)
                    .map((id) => document.getElementById(id)?.textContent ?? "")
                    .join(" "));
                const labelText = (item) => {
                    const clone = item.cloneNode(true);
                    clone.querySelectorAll("input,select,textarea,button").forEach((control) => control.remove());
                    return clone.textContent ?? "";
                };
                const label = element instanceof HTMLInputElement ||
                    element instanceof HTMLSelectElement ||
                    element instanceof HTMLTextAreaElement
                    ? normalize(Array.from(element.labels ?? [], labelText).join(" "))
                    : "";
                const text = normalize(element instanceof HTMLElement ? element.innerText : element.textContent);
                const alt = normalize(element.getAttribute("alt") ?? element.querySelector("img[alt]")?.getAttribute("alt"));
                const inputButtonName = element instanceof HTMLInputElement && ["button", "submit", "reset"].includes(element.type.toLowerCase())
                    ? normalize(element.value)
                    : "";
                const contentName = [
                    "button",
                    "cell",
                    "columnheader",
                    "gridcell",
                    "heading",
                    "link",
                    "menuitem",
                    "menuitemcheckbox",
                    "menuitemradio",
                    "option",
                    "row",
                    "rowheader",
                    "tab",
                    "tooltip",
                    "treeitem",
                ].includes(role)
                    ? text
                    : "";
                const name = normalize(element.getAttribute("aria-label")) ||
                    labelledBy ||
                    label ||
                    alt ||
                    inputButtonName ||
                    contentName ||
                    normalize(element.getAttribute("title"));
                return {
                    rect: clippedRect,
                    tag,
                    cssId: element.id ? `#${CSS.escape(element.id)}` : "",
                    role,
                    name,
                    label,
                    placeholder: normalize(element.getAttribute("placeholder")),
                    testId: normalize(element.getAttribute("data-testid")),
                    text: text.length <= 120 ? text : "",
                };
            }, { x: point.x, y: point.y });
            if (point.version !== this.#hoverVersion || point.generation !== this.#generation)
                return;
            if (!descriptor) {
                this.#clearHover();
                return;
            }
            const locator = formatHoverLocator(descriptor);
            const rect = descriptor.rect;
            const key = `${locator}|${Math.round(rect.x)}|${Math.round(rect.y)}|${Math.round(rect.width)}|${Math.round(rect.height)}`;
            if (key === this.#lastHoverKey)
                return;
            this.#lastHoverKey = key;
            this.#send({ type: "page.hover", rect, locator });
        }
        catch {
            if (point.version === this.#hoverVersion)
                this.#clearHover();
        }
    }
    #clearHover() {
        this.#hoverVersion++;
        this.#hoverPoint = undefined;
        if (this.#hoverTimer)
            clearTimeout(this.#hoverTimer);
        this.#hoverTimer = undefined;
        if (!this.#lastHoverKey)
            return;
        this.#lastHoverKey = undefined;
        this.#send({ type: "page.hover.clear" });
    }
    async #openSelectAt(page, x, y) {
        this.#clearHover();
        await this.#closeSelect();
        const handle = await page.evaluateHandle(({ x: targetX, y: targetY }) => {
            const target = document.elementFromPoint(targetX, targetY);
            if (target instanceof HTMLSelectElement)
                return target;
            return target?.closest("select") ?? null;
        }, { x, y });
        const element = handle.asElement();
        if (!element) {
            await handle.dispose();
            return false;
        }
        try {
            const descriptor = await element.evaluate((node, limits) => {
                if (!(node instanceof HTMLSelectElement))
                    return null;
                // ponytail: main-frame, single selects only; add frame/multi-select transport when product scope needs it.
                if (node.disabled || node.multiple || node.size > 1 || node.options.length > limits.maxOptions)
                    return null;
                const rect = node.getBoundingClientRect();
                if (rect.width < 1 || rect.height < 1 || node.options.length === 0)
                    return null;
                const options = Array.from(node.options, (option, index) => {
                    const group = option.parentElement instanceof HTMLOptGroupElement ? option.parentElement : null;
                    const label = `${group?.label ? `${group.label} — ` : ""}${option.label || option.textContent || `Opção ${index + 1}`}`;
                    return {
                        index,
                        label: label.slice(0, limits.maxLabelLength),
                        disabled: option.disabled || Boolean(group?.disabled),
                        selected: option.selected,
                    };
                });
                return { rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, options };
            }, { maxOptions: MAX_SELECT_OPTIONS, maxLabelLength: MAX_SELECT_LABEL_LENGTH });
            if (!descriptor) {
                await element.dispose();
                return false;
            }
            const id = ++this.#nextSelectId;
            this.#pendingSelect = {
                id,
                element,
                enabledIndices: new Set(descriptor.options.filter((option) => !option.disabled).map((option) => option.index)),
            };
            this.#send({ type: "page.select", selectId: id, rect: descriptor.rect, options: descriptor.options });
            return true;
        }
        catch {
            await element.dispose().catch(() => { });
            return false;
        }
    }
    async #chooseSelect(selectId, index) {
        const pending = this.#pendingSelect;
        if (!pending || pending.id !== selectId)
            throw new SessionError("INVALID_MESSAGE", "Seleção expirou. Abra o campo novamente.", true);
        if (index === null) {
            await this.#closeSelect();
            return;
        }
        if (!pending.enabledIndices.has(index))
            throw new SessionError("INVALID_MESSAGE", "Opção de select inválida.", true);
        try {
            await pending.element.selectOption({ index });
        }
        catch {
            throw new SessionError("INVALID_MESSAGE", "Select não está mais disponível.", true);
        }
        finally {
            await this.#closeSelect();
        }
    }
    async #runSteps(page, steps) {
        this.#clearHover();
        await this.#closeSelect();
        await this.#adapter?.whenIdle();
        this.#adapter?.pause();
        let timeout;
        try {
            await page.reload({ waitUntil: "domcontentloaded", timeout: NAVIGATION_TIMEOUT_MS });
            const AsyncFunction = Object.getPrototypeOf(async () => { }).constructor;
            const execute = new AsyncFunction("page", "expect", "process", steps);
            await Promise.race([
                execute(page, expect, process),
                new Promise((_, reject) => {
                    timeout = setTimeout(() => reject(new SessionError("SCRIPT_TIMEOUT", "Script excedeu 30 segundos.", true)), SCRIPT_TIMEOUT_MS);
                }),
            ]);
            this.#send({ type: "script.done" });
        }
        catch (error) {
            if (error instanceof SessionError)
                throw error;
            throw new SessionError("SCRIPT_FAILED", "Script não pôde ser executado.", true);
        }
        finally {
            if (timeout)
                clearTimeout(timeout);
            this.#adapter?.resume();
        }
    }
    async #closeSelect() {
        const pending = this.#pendingSelect;
        if (!pending)
            return;
        this.#pendingSelect = undefined;
        this.#send({ type: "page.select.close", selectId: pending.id });
        await pending.element.dispose().catch(() => { });
    }
    #failRecorder(error) {
        void this.#enqueueLifecycle(async () => {
            if (this.#status === "idle" || this.#status === "stopping")
                return;
            await this.#stopResources();
            this.#setStatus("error");
            this.#send({ type: "error", code: error.code, message: error.message, recoverable: false });
        });
    }
    #failUnexpectedBrowserClose() {
        void this.#enqueueLifecycle(async () => {
            if (this.#status !== "ready")
                return;
            await this.#stopResources();
            this.#setStatus("error");
            this.#send({
                type: "error",
                code: "BROWSER_FAILED",
                message: "Chromium encerrou inesperadamente.",
                recoverable: false,
            });
        });
    }
    async #stopResources() {
        this.#closingResources = true;
        this.#generation++;
        const cdp = this.#cdp;
        const adapter = this.#adapter;
        const page = this.#page;
        const context = this.#context;
        const browser = this.#browser;
        this.#cdp = undefined;
        this.#adapter = undefined;
        this.#page = undefined;
        this.#context = undefined;
        this.#browser = undefined;
        this.#pressedKeys.clear();
        this.#suppressPointerUp = false;
        this.#clearHover();
        this.#latestFrame = undefined;
        if (this.#frameTimer)
            clearTimeout(this.#frameTimer);
        this.#frameTimer = undefined;
        await this.#inputQueue;
        await this.#closeSelect();
        await cdp?.send("Page.stopScreencast").catch(() => { });
        await cdp?.detach().catch(() => { });
        await adapter?.close();
        await page?.close().catch(() => { });
        await context?.close().catch(() => { });
        await browser?.close().catch(() => { });
        this.#closingResources = false;
    }
    #setStatus(status) {
        this.#status = status;
        this.#sendState();
    }
    #sendState() {
        this.#send({
            type: "session.state",
            status: this.#status,
            ...(this.#targetUrl ? { url: this.#targetUrl } : {}),
        });
    }
    #hasResources() {
        return Boolean(this.#browser || this.#context || this.#page || this.#cdp || this.#adapter);
    }
    #enqueueLifecycle(task) {
        const operation = this.#lifecycle.then(task);
        this.#lifecycle = operation.then(() => undefined, () => undefined);
        return operation;
    }
}
function formatHoverLocator(descriptor) {
    if (descriptor.role && descriptor.name)
        return `getByRole(${quote(descriptor.role)}, { name: ${quote(descriptor.name)} })`;
    if (descriptor.label)
        return `getByLabel(${quote(descriptor.label)})`;
    if (descriptor.placeholder)
        return `getByPlaceholder(${quote(descriptor.placeholder)})`;
    if (descriptor.testId)
        return `getByTestId(${quote(descriptor.testId)})`;
    if (descriptor.role)
        return `getByRole(${quote(descriptor.role)})`;
    if (descriptor.text)
        return `getByText(${quote(descriptor.text)})`;
    if (descriptor.cssId)
        return `locator(${quote(descriptor.cssId)})`;
    return `locator(${quote(descriptor.tag)})`;
}
function quote(value) {
    return `'${value.replaceAll("\\", "\\\\").replaceAll("'", "\\'").replaceAll("\n", "\\n")}'`;
}
