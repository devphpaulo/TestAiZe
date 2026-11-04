const PASSWORD_EXPRESSION = 'process.env.PLAYWRIGHT_PASSWORD ?? ""';
export class RecorderAdapterError extends Error {
    code = "RECORDER_INCOMPATIBLE";
    constructor(message = "Recorder interno incompatível com Playwright 1.62.1.") {
        super(message);
        this.name = "RecorderAdapterError";
    }
}
export class PlaywrightRecorderAdapter {
    #context;
    #onCode;
    #onError;
    #snippets = [];
    #observedPages = new WeakSet();
    #lastUrl;
    #pending = Promise.resolve();
    #generation = 0;
    #paused = false;
    #closed = false;
    constructor(context, onCode, onError = () => { }) {
        this.#context = context;
        this.#onCode = onCode;
        this.#onError = onError;
    }
    async enable() {
        if (typeof this.#context._enableRecorder !== "function")
            throw new RecorderAdapterError();
        try {
            await this.#context._enableRecorder({ mode: "recording", recorderMode: "api", language: "playwright-test" }, {
                actionAdded: (page, action, code) => this.#enqueue(page, action, code, false),
                actionUpdated: (page, action, code) => this.#enqueue(page, action, code, true),
                signalAdded: () => { },
            });
        }
        catch {
            throw new RecorderAdapterError();
        }
        this.#emit();
    }
    clear() {
        this.#generation++;
        this.#snippets.length = 0;
        this.#emit();
    }
    async whenIdle() {
        await this.#pending;
    }
    pause() {
        this.#generation++;
        this.#paused = true;
    }
    resume() {
        this.#paused = false;
    }
    async close() {
        if (this.#closed)
            return;
        this.#closed = true;
        this.#generation++;
        await this.#pending;
        await this.#context._disableRecorder?.().catch(() => { });
    }
    #enqueue(page, event, code, update) {
        const generation = this.#generation;
        this.#pending = this.#pending
            .then(async () => {
            if (this.#closed || this.#paused || generation !== this.#generation)
                return;
            this.#observeNavigation(page);
            const snippet = await this.#safeSnippet(page, event, code);
            const previous = update ? this.#snippets.at(-1) : undefined;
            const url = page.url();
            const expectedUrl = !this.#snippets.length || isNavigationSnippet(snippet)
                ? undefined
                : previous?.expectedUrl ?? (url === this.#lastUrl ? undefined : url);
            this.#lastUrl = url;
            if (this.#closed || this.#paused || generation !== this.#generation)
                return;
            const recorded = { code: snippet, ...(expectedUrl ? { expectedUrl } : {}) };
            if (update && this.#snippets.length)
                this.#snippets[this.#snippets.length - 1] = recorded;
            else
                this.#snippets.push(recorded);
            this.#emit();
        })
            .catch((error) => {
            this.#onError(error instanceof RecorderAdapterError ? error : new RecorderAdapterError());
        });
    }
    async #safeSnippet(page, event, code) {
        const action = record(event.action);
        if (action?.name !== "fill")
            return code;
        let environmentKey = 'PLAYWRIGHT_PASSWORD';
        try {
            const selector = action.selector;
            const framePath = event.framePath;
            // ponytail: nested-frame fills stay masked; resolve frame paths when iframe recording enters MVP scope.
            if (typeof selector === "string" && (!Array.isArray(framePath) || framePath.length === 0)) {
                environmentKey = await page.locator(selector).first().evaluate((element) => {
                    if (!(element instanceof HTMLInputElement)) return null;
                    if (element.type.toLowerCase() === 'password') return 'PLAYWRIGHT_PASSWORD';
                    const identifiers = [element.id, element.name, element.autocomplete, element.getAttribute('aria-label'), element.placeholder,
                        ...Array.from(element.labels ?? []).map((label) => label.textContent)].join(' ').toLowerCase();
                    if (element.type.toLowerCase() === 'email' || /e[\s_-]?mail/.test(identifiers)) return 'PLAYWRIGHT_EMAIL';
                    return null;
                });
            }
        }
        catch {
            environmentKey = 'PLAYWRIGHT_PASSWORD';
        }
        return environmentKey ? redactFillCode(code, environmentKey) : code;
    }
    #emit() {
        const steps = this.#snippets.map(({ code, expectedUrl }) => expectedUrl ? `${code.trimEnd()}\nawait expect(page).toHaveURL(${quote(expectedUrl)});` : code);
        this.#onCode(buildSource(steps), steps.join("\n"));
    }
    #observeNavigation(page) {
        if (this.#observedPages.has(page))
            return;
        this.#observedPages.add(page);
        page.on("framenavigated", (frame) => {
            if (this.#closed || this.#paused || frame !== page.mainFrame())
                return;
            const url = frame.url();
            this.#lastUrl = url;
            const latest = this.#snippets.at(-1);
            if (!latest || latest.expectedUrl || isNavigationSnippet(latest.code))
                return;
            latest.expectedUrl = url;
            this.#emit();
        });
    }
}
export function buildSource(snippets) {
    const body = snippets
        .flatMap((snippet) => snippet.trim().split("\n"))
        .map((line) => `  ${line}`)
        .join("\n");
    return `import { test, expect } from '@playwright/test';\n\ntest('recorded flow', async ({ page }) => {\n${body}${body ? "\n" : ""}});\n`;
}
export function redactFillCode(code, environmentKey = 'PLAYWRIGHT_PASSWORD') {
    const trimmed = code.trimEnd();
    const marker = ".fill(";
    const start = trimmed.lastIndexOf(marker);
    const hasSemicolon = trimmed.endsWith(");");
    const hasClosingParenthesis = hasSemicolon || trimmed.endsWith(")");
    if (start < 0 || !hasClosingParenthesis)
        throw new RecorderAdapterError();
    const suffix = hasSemicolon ? ");" : ")";
    const expression = environmentKey === 'PLAYWRIGHT_EMAIL' ? 'process.env.PLAYWRIGHT_EMAIL ?? ""' : PASSWORD_EXPRESSION;
    return `${trimmed.slice(0, start + marker.length)}${expression}${suffix}${code.slice(trimmed.length)}`;
}
function record(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value)
        ? value
        : undefined;
}
function quote(value) {
    return `'${value.replaceAll("\\", "\\\\").replaceAll("'", "\\'").replaceAll("\n", "\\n")}'`;
}
function isNavigationSnippet(code) {
    return code.includes("page.goto(");
}
