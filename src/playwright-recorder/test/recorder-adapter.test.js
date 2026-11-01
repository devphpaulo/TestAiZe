import assert from "node:assert/strict";
import { test } from "node:test";
import { randomUUID } from "node:crypto";
import { PlaywrightRecorderAdapter, RecorderAdapterError, buildSource, redactFillCode, } from "../playwright-recorder-adapter.js";
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
