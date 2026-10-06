import assert from "node:assert/strict";
import { createServer } from "node:http";
import { after, before, test } from "node:test";
import { randomUUID } from "node:crypto";
import { chromium } from "../runtime.js";
import { PlaywrightRecorderAdapter, RecorderAdapterError, buildSource, redactFillCode, } from "../playwright-recorder-adapter.js";
let browser;
before(async () => {
    browser = await chromium.launch({ headless: true });
});
after(async () => {
    await browser?.close();
});
test("builds a complete test and redacts fill without retaining its value", () => {
    const secret = `canary-${randomUUID()}`;
    const redacted = redactFillCode(`await page.getByLabel('Password').fill(${JSON.stringify(secret)});`);
    const source = buildSource([redacted]);
    assert.match(source, /process\.env\.PLAYWRIGHT_PASSWORD/);
    assert.equal(source.includes(secret), false, "Generated code leaked canary.");
    assert.match(source, /test\('recorded flow'/);
});
test("fails clearly when private recorder API is unavailable", async () => {
    const context = {};
    const adapter = new PlaywrightRecorderAdapter(context, () => { });
    await assert.rejects(adapter.enable(), RecorderAdapterError);
    const brokenContext = {
        _enableRecorder: async () => {
            throw new Error("private failure");
        },
    };
    await assert.rejects(new PlaywrightRecorderAdapter(brokenContext, () => { }).enable(), RecorderAdapterError);
});
test("adds URL assertion when navigation follows the recorder action", async () => {
    let sink = {};
    const context = { _enableRecorder: async (_options, recorderSink) => { sink = recorderSink; } };
    let url = "https://example.test/";
    const listeners = new Map();
    const frame = { url: () => url };
    const page = {
        url: () => url,
        mainFrame: () => frame,
        on: (event, listener) => listeners.set(event, listener),
    };
    const updates = [];
    const adapter = new PlaywrightRecorderAdapter(context, (code) => updates.push(code));
    await adapter.enable();
    sink.actionAdded?.(page, { action: { name: "navigate" } }, "await page.goto('https://example.test/');");
    sink.actionAdded?.(page, { action: { name: "click" } }, "await page.getByRole('link', { name: 'Search' }).click();");
    await adapter.whenIdle();
    url = "https://example.test/search";
    listeners.get("framenavigated")?.(frame);
    assert.ok((updates.at(-1) ?? "").includes("await expect(page).toHaveURL('https://example.test/search');"));
    await adapter.close();
});
test("fails closed when fill target cannot be classified and replaces updated action", async () => {
    let sink = {};
    const context = {
        _enableRecorder: async (_options, recorderSink) => {
            sink = recorderSink;
        },
        _disableRecorder: async () => { },
    };
    const page = {
        url: () => "http://fixture.test/",
        on: () => { },
        locator: () => {
            throw new Error("classification failed");
        },
    };
    const updates = [];
    const adapter = new PlaywrightRecorderAdapter(context, (code) => updates.push(code));
    const secret = `canary-${randomUUID()}`;
    await adapter.enable();
    sink.actionAdded?.(page, { action: { name: "fill", selector: "missing" } }, `await page.locator('missing').fill(${JSON.stringify(secret)});`);
    await adapter.whenIdle();
    assert.match(updates.at(-1) ?? "", /PLAYWRIGHT_PASSWORD/);
    assert.equal((updates.at(-1) ?? "").includes(secret), false, "Fail-closed code leaked canary.");
    sink.actionUpdated?.(page, { action: { name: "click", selector: "button" } }, "await page.getByRole('button').dblclick();");
    await adapter.whenIdle();
    assert.match(updates.at(-1) ?? "", /\.dblclick\(\)/);
    assert.doesNotMatch(updates.at(-1) ?? "", /locator\('missing'\)/);
    await adapter.close();
});
test("Playwright 1.62.1 recorder emits navigation, click, fill, and masks password", async () => {
    const fixture = await serveFixture();
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    const page = await context.newPage();
    const updates = [];
    const errors = [];
    let adapter;
    try {
        adapter = new PlaywrightRecorderAdapter(context, (code) => updates.push(code), (error) => errors.push(error));
        await adapter.enable();
        await page.goto(fixture.url);
        await page.getByRole("link", { name: "Search" }).click();
        await page.getByRole("button", { name: "Run" }).click();
        await page.getByLabel("Name").fill("Ada");
        const secret = `canary-${randomUUID()}`;
        await page.getByLabel("Password").fill(secret);
        await waitFor(() => {
            const code = updates.at(-1) ?? "";
            return code.includes(".click()") && code.includes(".fill('Ada')") && code.includes("PLAYWRIGHT_PASSWORD");
        });
        await adapter.whenIdle();
        const code = updates.at(-1) ?? "";
        assert.match(code, /page\.goto/);
        assert.match(code, /expect\(page\)\.toHaveURL\(/);
        assert.equal(code.includes(`await expect(page).toHaveURL('${new URL(fixture.url).href}');`), false);
        assert.ok(code.includes(`await expect(page).toHaveURL('${new URL("/search", fixture.url).href}');`));
        assert.match(code, /\.click\(\)/);
        assert.match(code, /\.fill\('Ada'\)/);
        assert.match(code, /process\.env\.PLAYWRIGHT_PASSWORD/);
        assert.equal(code.includes(secret), false, "Generated code leaked canary.");
        assert.deepEqual(errors, []);
        adapter.clear();
        assert.doesNotMatch(updates.at(-1) ?? "", /page\.goto|\.click\(|\.fill\(/);
    }
    finally {
        await adapter?.close();
        await context.close();
        await fixture.close();
    }
});
async function serveFixture() {
    const server = createServer((_request, response) => {
        response.setHeader("Content-Type", "text/html; charset=utf-8");
        response.end(`<!doctype html><a href="/search">Search</a><label>Name <input aria-label="Name"></label><label>Password <input aria-label="Password" type="password"></label><button>Run</button>`);
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string")
        throw new Error("Fixture server did not bind to TCP.");
    return {
        url: `http://127.0.0.1:${address.port}`,
        close: () => new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve()))),
    };
}
async function waitFor(predicate, timeoutMs = 5_000) {
    const deadline = Date.now() + timeoutMs;
    while (!predicate()) {
        if (Date.now() >= deadline)
            throw new Error("Timed out waiting for recorder output.");
        await new Promise((resolve) => setTimeout(resolve, 25));
    }
}
