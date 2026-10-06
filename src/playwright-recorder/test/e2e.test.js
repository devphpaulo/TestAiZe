import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer as createHttpServer } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "../runtime.js";
import WebSocket from "../vendor/ws/wrapper.mjs";
import { RecorderSession, SessionError } from "../recorder-session.js";
import { createServer } from "../server.js";
test("HTTP contract and WebSocket origin policy stay local", async () => {
    const recorder = createServer();
    const port = await recorder.listen(0);
    try {
        const health = await fetch(`http://127.0.0.1:${port}/health`);
        assert.equal(health.status, 200);
        assert.deepEqual(await health.json(), { status: "ok" });
        const styles = await fetch(`http://127.0.0.1:${port}/sleek.css`);
        assert.equal(styles.status, 200);
        assert.match(await styles.text(), /Sleek/);
        assert.equal((await fetch(`http://127.0.0.1:${port}/missing`)).status, 404);
        assert.equal((await fetch(`http://127.0.0.1:${port}/..%2fpackage.json`)).status, 404);
        assert.equal(await rejectedStatus(`ws://127.0.0.1:${port}/ws`, "http://example.test"), 403);
        assert.equal(await rejectedStatus(`ws://127.0.0.1:${port}/other`, `http://127.0.0.1:${port}`), 404);
        const origin = `http://127.0.0.1:${port}`;
        const first = new WebSocket(`ws://127.0.0.1:${port}/ws`, { origin });
        await once(first, "open");
        const invalidMessage = waitForSocketMessage(first, "error");
        first.send("{");
        assert.equal((await invalidMessage).code, "INVALID_MESSAGE");
        assert.equal((await fetch(`http://127.0.0.1:${port}/health`)).status, 200);
        const firstClosed = once(first, "close");
        const second = new WebSocket(`ws://127.0.0.1:${port}/ws`, { origin });
        await once(second, "open");
        const [closeCode] = await firstClosed;
        assert.equal(closeCode, 1012);
        const oversizedClosed = once(second, "close");
        second.send("x".repeat(64 * 1024 + 1));
        const [oversizedCode] = await oversizedClosed;
        assert.equal(oversizedCode, 1009);
        assert.equal((await fetch(`http://127.0.0.1:${port}/health`)).status, 200);
    }
    finally {
        await recorder.close();
    }
});
test("user records navigation, click, text, password, clear, and stop inside UI", async () => {
    const fixture = await serveFixture();
    const recorder = createServer();
    const port = await recorder.listen(0);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
    const browserOutput = [];
    page.on("console", (message) => browserOutput.push(message.text()));
    page.on("pageerror", (error) => browserOutput.push(error.message));
    try {
        await page.goto(`http://127.0.0.1:${port}`);
        await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
            origin: `http://127.0.0.1:${port}`,
        });
        await page.getByLabel("URL HTTP ou HTTPS").fill("http://127.0.0.1:1");
        await page.getByRole("button", { name: "Iniciar" }).click();
        await waitFor(page, () => document.querySelector("#status")?.textContent === "Não foi possível abrir o destino.");
        await page.getByLabel("URL HTTP ou HTTPS").fill(fixture.url);
        await page.getByRole("button", { name: "Iniciar" }).click();
        await waitFor(page, () => document.querySelector("#status")?.textContent === "Pronto");
        await waitFor(page, () => Number(document.querySelector("#viewport")?.getAttribute("data-frame-count")) > 0);
        await hoverViewport(page, 90, 440);
        const hoverTooltip = page.locator("#hover-tooltip");
        await hoverTooltip.waitFor({ state: "visible" });
        assert.equal(await page.locator("#hover-locator").textContent(), "getByRole('link', { name: 'Sauce Demo' })");
        const tooltipColors = await hoverTooltip.evaluate((element) => {
            const styles = getComputedStyle(element);
            return { backgroundColor: styles.backgroundColor, color: styles.color };
        });
        assert.notEqual(tooltipColors.backgroundColor, tooltipColors.color);
        assert.equal(await page.locator("#hover-highlight").isVisible(), true);
        await hoverViewport(page, 160, 160);
        await waitFor(page, () => document.querySelector("#hover-locator")?.textContent === "getByLabel('Password')");
        await hoverViewport(page, 90, 440);
        await hoverViewport(page, 160, 370);
        await waitFor(page, () => document.querySelector("#hover-locator")?.textContent === "getByRole('combobox', { name: 'Role' })");
        await page.getByLabel("URL HTTP ou HTTPS").hover();
        await hoverTooltip.waitFor({ state: "hidden" });
        await page.getByLabel("URL HTTP ou HTTPS").focus();
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.activeElement?.id), "start");
        await page.keyboard.press("Tab");
        assert.equal(await page.evaluate(() => document.activeElement?.id), "stop");
        await clickViewport(page, 160, 80);
        await page.keyboard.press("CapsLock");
        await page.keyboard.type("P");
        await page.keyboard.press("CapsLock");
        await page.keyboard.type("aulo ");
        await page.keyboard.press("CapsLock");
        await page.keyboard.type("H");
        await page.keyboard.press("CapsLock");
        await page.keyboard.type("enrique");
        await page.locator("#viewport").evaluate((element) => {
            const event = new Event("paste", { bubbles: true, cancelable: true });
            Object.defineProperty(event, "clipboardData", { value: { getData: () => " Ω" } });
            element.dispatchEvent(event);
        });
        await clickViewport(page, 100, 230);
        const secret = `canary-${randomUUID()}`;
        await clickViewport(page, 160, 160);
        await page.keyboard.type(secret);
        await clickViewport(page, 160, 370);
        const selectOverlay = page.getByRole("listbox", { name: "Opções do campo selecionado" });
        await selectOverlay.waitFor({ state: "visible" });
        assert.equal(await page.getByRole("option", { name: "Disabled" }).isDisabled(), true);
        await page.getByRole("option", { name: "Manager" }).click();
        await selectOverlay.waitFor({ state: "hidden" });
        await waitFor(page, () => {
            const code = document.querySelector("#code")?.value ?? "";
            return code.includes("page.goto") && code.includes(".click()") && code.includes(".fill('Paulo Henrique Ω')") && code.includes("PLAYWRIGHT_PASSWORD") && code.includes(".selectOption(");
        });
        const code = await page.getByLabel("Código Playwright Test gerado").inputValue();
        assert.match(code, /page\.goto/);
        assert.match(code, /getByRole\('button', \{ name: 'Run' \}\)\.click/);
        assert.match(code, /\.fill\('Paulo Henrique Ω'\)/);
        assert.match(code, /\.selectOption\('manager'\)/);
        assert.equal(code.includes("Sauce Demo"), false, "Hover locator leaked into recorded actions.");
        assert.equal(code.includes("CapsLock"), false, "Generated code retained local CapsLock actions.");
        assert.equal(code.match(/getByRole\('textbox', \{ name: 'Name' \}\)\.fill/g)?.length, 1, "Generated code should retain one final fill for the field.");
        assert.match(code, /process\.env\.PLAYWRIGHT_PASSWORD/);
        assert.equal(code.includes(secret), false, "UI code leaked canary.");
        assert.equal(browserOutput.some((line) => line.includes(secret)), false, "Browser output leaked canary.");
        await page.getByRole("button", { name: "Copiar" }).click();
        await waitFor(page, () => document.querySelector("#copy-status")?.textContent === "Código copiado.");
        assert.equal(normalizeEndings(await page.evaluate(() => navigator.clipboard.readText())), normalizeEndings(code));
        await page.locator("#viewport").hover();
        await page.mouse.wheel(0, 120);
        const requestsBeforeRestart = fixture.cookies.length;
        const framesBeforeRestart = Number(await page.locator("#viewport").getAttribute("data-frame-count"));
        await page.getByRole("button", { name: "Iniciar" }).click();
        await poll(() => fixture.cookies.length > requestsBeforeRestart);
        await waitFor(page, () => {
            const value = document.querySelector("#code")?.value ?? "";
            return document.querySelector("#status")?.textContent === "Pronto" && value.includes("page.goto") && !value.includes("PLAYWRIGHT_PASSWORD");
        });
        await page.waitForFunction((count) => Number(document.querySelector("#viewport")?.getAttribute("data-frame-count")) > count, framesBeforeRestart);
        assert.equal(fixture.cookies.at(-1), undefined);
        await page.getByRole("button", { name: "Limpar" }).click();
        await waitFor(page, () => {
            const value = document.querySelector("#code")?.value ?? "";
            return value.includes("recorded flow") && !value.includes("page.goto") && !value.includes(".fill(");
        });
        assert.equal(await page.locator("#status").textContent(), "Pronto");
        await page.getByRole('tab', { name: 'Etapas para executar' }).click();
        await page.getByLabel("Etapas Playwright executáveis").fill("await page.getByRole('button', { name: 'Run' }).click();");
        await page.getByRole("button", { name: "Rodar" }).click();
        await page.getByRole('dialog').getByRole('button', { name: 'Rodar etapas', exact: true }).click();
        await waitFor(page, () => document.querySelector("#copy-status")?.textContent === "Etapas executadas.");
        await page.getByRole("button", { name: "Encerrar" }).click();
        await waitFor(page, () => document.querySelector("#status")?.textContent === "Ocioso");
    }
    finally {
        await page.close();
        await browser.close();
        await recorder.close();
        await fixture.close();
    }
});
test("session keeps one recent frame under backpressure and closes idempotently", async () => {
    const fixture = await serveFixture();
    const messages = [];
    let blocked = true;
    let frameAttempts = 0;
    let deliveredFrames = 0;
    const session = new RecorderSession((message) => {
        if (message.type === "page.frame") {
            frameAttempts++;
            if (blocked)
                return false;
            deliveredFrames++;
            return true;
        }
        messages.push(message);
        return true;
    });
    try {
        await session.start(fixture.url);
        await poll(() => frameAttempts > 0);
        await session.handleInput({ type: "input.pointer", phase: "down", x: 100, y: 230, button: "left", clickCount: 1 });
        await session.handleInput({ type: "input.pointer", phase: "up", x: 100, y: 230, button: "left", clickCount: 1 });
        await poll(() => messages.some((message) => message.type === "recording.code" && String(message.code).includes(".click()")));
        await session.handleInput({ type: "input.pointer", phase: "down", x: 160, y: 370, button: "left", clickCount: 1 });
        await session.handleInput({ type: "input.pointer", phase: "up", x: 160, y: 370, button: "left", clickCount: 1 });
        const selectMessage = messages.find((message) => message.type === "page.select");
        assert.ok(selectMessage);
        const selectId = Number(selectMessage.selectId);
        await assert.rejects(session.handleInput({ type: "input.select", selectId, index: 2 }), (error) => error instanceof SessionError && error.code === "INVALID_MESSAGE");
        await session.handleInput({ type: "input.select", selectId, index: 1 });
        await poll(() => messages.some((message) => message.type === "recording.code" && String(message.code).includes("selectOption('manager')")));
        blocked = false;
        await poll(() => deliveredFrames > 0);
        await Promise.all([session.close(), session.close()]);
        assert.equal(session.status, "idle");
        const attemptsAfterClose = frameAttempts;
        await new Promise((resolve) => setTimeout(resolve, 50));
        assert.equal(frameAttempts, attemptsAfterClose);
    }
    finally {
        await session.close();
        await fixture.close();
    }
});
async function clickViewport(page, targetX, targetY) {
    const box = await page.locator("#viewport").boundingBox();
    if (!box)
        throw new Error("Viewport canvas is not visible.");
    await page.mouse.click(box.x + (targetX / 1280) * box.width, box.y + (targetY / 720) * box.height);
}
async function hoverViewport(page, targetX, targetY) {
    const box = await page.locator("#viewport").boundingBox();
    if (!box)
        throw new Error("Viewport canvas is not visible.");
    await page.mouse.move(box.x + (targetX / 1280) * box.width, box.y + (targetY / 720) * box.height);
}
async function waitFor(page, predicate, timeout = 10_000) {
    await page.waitForFunction(predicate, undefined, { timeout });
}
async function poll(predicate, timeout = 10_000) {
    const deadline = Date.now() + timeout;
    while (!predicate()) {
        if (Date.now() >= deadline)
            throw new Error("Timed out waiting for local condition.");
        await new Promise((resolve) => setTimeout(resolve, 25));
    }
}
async function serveFixture() {
    const html = await readFile(fileURLToPath(new URL("./fixture.html", import.meta.url)));
    const cookies = [];
    const server = createHttpServer((request, response) => {
        if (request.url === "/fixture")
            cookies.push(request.headers.cookie);
        response
            .writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Set-Cookie": "fixture-session=temporary; Path=/" })
            .end(html);
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address();
    if (!address || typeof address === "string")
        throw new Error("Fixture server did not bind to TCP.");
    return {
        url: `http://127.0.0.1:${address.port}/fixture`,
        cookies,
        close: () => new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve()))),
    };
}
function rejectedStatus(url, origin) {
    return new Promise((resolve, reject) => {
        const socket = new WebSocket(url, { origin });
        socket.once("unexpected-response", (_request, response) => {
            resolve(response.statusCode ?? 0);
            response.resume();
        });
        socket.once("open", () => {
            socket.close();
            reject(new Error("WebSocket policy unexpectedly accepted connection."));
        });
        socket.once("error", () => { });
    });
}
function waitForSocketMessage(socket, type) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            cleanup();
            reject(new Error(`Timed out waiting for WebSocket message: ${type}`));
        }, 5_000);
        const onMessage = (data) => {
            const message = JSON.parse(data.toString());
            if (message.type !== type)
                return;
            cleanup();
            resolve(message);
        };
        const cleanup = () => {
            clearTimeout(timeout);
            socket.off("message", onMessage);
        };
        socket.on("message", onMessage);
    });
}
function normalizeEndings(value) {
    return value.replaceAll("\r\n", "\n");
}
