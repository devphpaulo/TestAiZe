import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { createInterface } from "node:readline";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "../runtime.js";
const root = fileURLToPath(new URL("../../../", import.meta.url));
test("separate Automation page records through embedded Chromium and cleans up on reload and exit", { timeout: 90000 }, async () => {
    const dataRoot = await mkdtemp(resolve(tmpdir(), "testaize-recorder-"));
    const executable = process.env.TESTAIZE_EXE;
    const python = process.env.TESTAIZE_PYTHON || resolve(root, ".venv/Scripts/python.exe");
    const host = executable
        ? spawn(executable, ["--data-dir", dataRoot, "--no-browser", "--no-tray"], { stdio: ["pipe", "pipe", "pipe"] })
        : spawn(python, [resolve(root, "tests/automation_host_fixture.py"), dataRoot], { stdio: ["pipe", "pipe", "pipe"] });
    host.stderr.resume();
    const lines = createInterface({ input: host.stdout });
    const ready = new Promise((resolveReady, reject) => {
        const deadline = setTimeout(() => reject(new Error("Flask host readiness timed out")), 15000);
        lines.on("line", (line) => {
            if (line.startsWith("HOST_READY ")) {
                clearTimeout(deadline);
                resolveReady(line.slice(11));
            }
        });
        host.once("error", (error) => { clearTimeout(deadline); reject(error); });
        host.once("exit", () => { clearTimeout(deadline); reject(new Error("Flask host exited before readiness")); });
    });
    // A windowed release executable writes runtime.json instead of stdout.
    if (executable)
        void ready.catch(() => { });
    const fixture = createServer((_request, response) => {
        response.setHeader("Content-Type", "text/html; charset=utf-8");
        response.end('<!doctype html><title>Catálogo de teste</title><h1>Catálogo</h1><input aria-label="Busca" style="position:absolute;left:40px;top:80px;width:240px;height:40px"><button style="position:absolute;left:40px;top:140px;width:120px;height:40px" onclick="document.querySelector(\'output\').textContent=document.querySelector(\'#email\').value===\'vault@example.test\' && document.querySelector(\'#password\').value===\'vault-secret-shutdown-canary\'?\'Cofre OK\':\'Encontrado\'">Buscar</button><output style="position:absolute;left:40px;top:200px"></output><input id="email" type="email" aria-label="E-mail" style="position:absolute;left:40px;top:240px;width:240px;height:40px"><input id="password" type="password" aria-label="Password" style="position:absolute;left:40px;top:300px;width:240px;height:40px">');
    });
    fixture.listen(0, "127.0.0.1");
    await once(fixture, "listening");
    const address = fixture.address();
    assert.ok(address && typeof address !== "string");
    const fixtureUrl = `http://127.0.0.1:${address.port}`;
    let browser;
    try {
        let origin = executable ? "" : await ready;
        if (executable) {
            const deadline = Date.now() + 15000;
            while (!origin && Date.now() < deadline) {
                try {
                    origin = `http://127.0.0.1:${JSON.parse(await readFile(resolve(dataRoot, "config/runtime.json"), "utf8")).port}`;
                }
                catch {
                    await new Promise((resume) => setTimeout(resume, 100));
                }
            }
            assert.ok(origin, "Release executable must publish runtime.json");
        }
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.goto(origin);
        assert.equal((await (await page.request.get(origin + "/api/iniciativas/automacao/recorder/status")).json()).state, "idle");
    await page.getByRole("link", { name: "Automação", exact: true }).click();
    assert.equal(await page.locator('.automation-frame-shell iframe').count(), 0);
    await page.getByRole('link', { name: 'Gravar teste avulso' }).click();
        const iframe = page.locator(".automation-frame-shell iframe");
        await iframe.waitFor();
        assert.equal(await page.locator('#automation-retry').isVisible(), false);
        const workerUrl = (await iframe.getAttribute("src"));
        const worker = page.frameLocator(".automation-frame-shell iframe");
        await worker.locator("#status").filter({ hasText: "Ocioso" }).waitFor();
        assert.equal(await worker.locator(".hero").isVisible(), false);
        await worker.getByLabel("URL HTTP ou HTTPS").fill(fixtureUrl);
        await worker.getByRole("button", { name: "Iniciar", exact: true }).click();
        await worker.locator("#status").filter({ hasText: "Pronto" }).waitFor();
        await worker.locator('#viewport[data-frame-count]').waitFor();
        assert.match(await worker.locator("#code").inputValue(), /page\.goto/);
        const canvas = worker.locator('#viewport');
        const box = await canvas.boundingBox();
        assert.ok(box);
        await page.mouse.click(box.x + 100 * box.width / 1280, box.y + 100 * box.height / 720);
        await page.keyboard.type('Produto QA');
        await page.mouse.click(box.x + 90 * box.width / 1280, box.y + 160 * box.height / 720);
        const deadline = Date.now() + 5000;
        while (!(await worker.locator('#code').inputValue()).includes("getByRole('button', { name: 'Buscar' }).click()") && Date.now() < deadline) {
            await new Promise((resume) => setTimeout(resume, 50));
        }
        assert.match(await worker.locator('#code').inputValue(), /Produto QA/);
        assert.match(await worker.locator('#code').inputValue(), /\.click\(\)/);
        // Values are updated while Chromium is already running, without reconnecting.
        await page.getByRole('button', { name: 'Cofre', exact: true }).click();
        const vault = page.locator('#vault-dialog');
        const emailEntry = vault.locator('.vault-entry').filter({ hasText: 'PLAYWRIGHT_EMAIL' });
        await emailEntry.getByLabel('Valor de PLAYWRIGHT_EMAIL').fill('vault@example.test');
        await emailEntry.getByRole('button', { name: 'Salvar', exact: true }).click();
        await vault.locator('#vault-feedback').filter({ hasText: 'Cofre atualizado.' }).waitFor();
        const passwordEntry = vault.locator('.vault-entry').filter({ hasText: 'PLAYWRIGHT_PASSWORD' });
        await passwordEntry.getByLabel('Valor de PLAYWRIGHT_PASSWORD').fill('vault-secret-shutdown-canary');
        await passwordEntry.getByRole('button', { name: 'Salvar', exact: true }).click();
        await passwordEntry.locator('.vault-saved-state').filter({ hasText: 'Valor salvo nesta execução' }).waitFor();
        assert.equal(await passwordEntry.getByLabel('Valor de PLAYWRIGHT_PASSWORD').inputValue(), 'vault-secret-shutdown-canary');
        assert.equal(await passwordEntry.getByLabel('Valor de PLAYWRIGHT_PASSWORD').getAttribute('type'), 'password');
        if (process.env.TESTAIZE_SCREENSHOT) await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT.replace('.png', '-cofre.png'), fullPage: true });
        await vault.getByRole('button', { name: 'Fechar Cofre' }).click();
        await page.mouse.click(box.x + 100 * box.width / 1280, box.y + 260 * box.height / 720);
        await page.keyboard.type('recorded-canary@example.test');
        await page.mouse.click(box.x + 100 * box.width / 1280, box.y + 320 * box.height / 720);
        await page.keyboard.type('recorded-password-canary');
        const credentialsDeadline = Date.now() + 5000;
        while (!(await worker.locator('#code').inputValue()).includes('PLAYWRIGHT_PASSWORD') && Date.now() < credentialsDeadline) await new Promise((resume) => setTimeout(resume, 50));
        const generated = await worker.locator('#code').inputValue();
        assert.match(generated, /process.env.PLAYWRIGHT_EMAIL/);
        assert.match(generated, /process.env.PLAYWRIGHT_PASSWORD/);
        assert.equal(generated.includes('recorded-canary@example.test') || generated.includes('recorded-password-canary'), false);
        await worker.getByRole('tab', { name: 'Etapas para executar' }).click();
        await worker.locator('#steps').fill((await worker.locator('#steps').inputValue()) + "\nawait page.getByRole('button', { name: 'Buscar' }).click();\nawait expect(page.locator('output')).toHaveText('Cofre OK');");
        await worker.getByRole('button', { name: 'Rodar', exact: true }).click();
        await worker.getByRole('dialog').getByRole('button', { name: 'Rodar etapas', exact: true }).click();
        await worker.locator('#copy-status').filter({ hasText: 'Etapas executadas.' }).waitFor();
        // Theme follows the host without reconnecting or losing the recording.
        await page.locator("#theme-toggle").click();
        const expectedTheme = await page.locator("html").getAttribute("data-theme");
        await worker.locator(`html[data-theme="${expectedTheme}"]`).waitFor();
        const runContrast = await worker.locator('#run').evaluate((button) => {
            const styles = getComputedStyle(button);
            function luminance(value) {
                const rgb = value.match(/\d+/g).slice(0, 3).map(Number).map((channel) => {
                    const normalized = channel / 255;
                    return normalized <= .04045 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4;
                });
                return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
            }
            const foreground = luminance(styles.color), background = luminance(styles.backgroundColor);
            return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
        });
        assert.ok(runContrast >= 4.5, `Rodar contrast is ${runContrast}`);
        if (process.env.TESTAIZE_SCREENSHOT)
            await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT, fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.waitForFunction(() => Number.parseInt(document.querySelector('iframe').style.height, 10) > 1000);
        assert.equal(await page.getByRole('link', { name: 'Automação', exact: true }).isVisible(), true);
        if (process.env.TESTAIZE_SCREENSHOT)
            await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT.replace('.png', '-mobile.png'), fullPage: true });
        const overflow = await page.evaluate(() => [...document.querySelectorAll('body *')].filter((element) => element.getBoundingClientRect().right > window.innerWidth).map((element) => element.className));
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, JSON.stringify(overflow));
        await page.setViewportSize({ width: 1500, height: 1100 });
        const downloadReady = page.waitForEvent('download');
        await worker.getByRole('button', { name: 'Salvar .spec.ts', exact: true }).click();
        const specDownload = await downloadReady;
        assert.equal(specDownload.suggestedFilename(), 'teste-gravado.spec.ts');
        assert.match(await readFile(await specDownload.path(), 'utf8'), /PLAYWRIGHT_PASSWORD/);
        await page.getByRole('button', { name: 'Salvar na biblioteca' }).click();
        await page.locator('#save-script-name').fill('Fluxo catálogo');
        await page.locator('#save-new-folder-name').fill('Catálogo');
        await page.locator('#save-new-cycle-name').fill('Smoke');
        await page.getByRole('button', { name: 'Salvar script', exact: true }).click();
        await page.locator('#automation-save-dialog').waitFor({ state: 'hidden' });
        const savedLink = await page.getByRole('link', { name: 'Abrir script na biblioteca' }).getAttribute('href');
        await page.reload();
        await page.locator(".automation-frame-shell iframe").waitFor();
        const replacementUrl = (await page.locator(".automation-frame-shell iframe").getAttribute("src"));
        assert.notEqual(new URL(replacementUrl).port, new URL(workerUrl).port);
        await assert.rejects(fetch(new URL("/health", workerUrl)));
        await page.getByRole("button", { name: "Encerrar gravação" }).click();
        await page.waitForURL(origin + "/iniciativas/automacao");
        assert.equal((await (await page.request.get(origin + "/api/iniciativas/automacao/recorder/status")).json()).state, "idle");
        await assert.rejects(fetch(new URL("/health", replacementUrl)));
        await page.goto(origin + savedLink);
        assert.match(await page.locator('#script-code').inputValue(), /process.env.PLAYWRIGHT_EMAIL/);
        await page.getByRole('button', { name: 'Rodar ciclo', exact: true }).click();
        await page.locator('#suite-passed').filter({ hasText: /^1$/ }).waitFor();
        await page.locator('#suite-state').filter({ hasText: 'Execução concluída' }).waitFor();
        assert.equal(await page.locator('#suite-failed').textContent(), '0');
        await page.locator('#script-code').fill((await page.locator('#script-code').inputValue()) + "\ntest('falha proposital', () => { expect(1).toBe(2); });");
        await page.getByRole('button', { name: 'Salvar alterações' }).click();
        await page.locator('#automation-library-feedback').filter({ hasText: 'Script salvo' }).waitFor();
        await page.getByRole('button', { name: 'Rodar ciclo', exact: true }).click();
        await page.locator('#suite-total').filter({ hasText: /^2$/ }).waitFor();
        await page.locator('#suite-failed').filter({ hasText: /^1$/ }).waitFor();
        await page.locator('#suite-state').filter({ hasText: 'Execução concluída' }).waitFor();
        assert.equal(await page.locator('#suite-passed').textContent(), '1');
        await page.getByText('Motivo da falha', { exact: true }).click();
        assert.match(await page.locator('#suite-results pre').textContent(), /toBe/);
        if (process.env.TESTAIZE_SCREENSHOT) { await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT.replace('.png', '-suite.png'), fullPage: true }); }
        await page.getByRole('link', { name: 'Voltar à pasta' }).click();
        assert.equal(await page.locator('.automation-history-row').count(), 2);
        if (process.env.TESTAIZE_SCREENSHOT) { await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT.replace('.png', '-library.png'), fullPage: true }); }
        assert.deepEqual(errors, []);
    }
    finally {
        await browser?.close();
        if (host.exitCode === null) {
            const stopped = once(host, "exit");
            if (executable && process.platform === 'win32') {
                const kill = spawn('taskkill', ['/PID', String(host.pid), '/T', '/F'], { stdio: 'ignore' });
                await once(kill, 'exit');
            }
            else if (executable)
                host.kill();
            else
                host.stdin.end("shutdown\n");
            await stopped;
        }
        fixture.close();
        await rm(dataRoot, { recursive: true, force: true });
    }
});

test('startup without Node keeps manual application running and hides Automation', { timeout: 30000 }, async () => {
    const dataRoot = await mkdtemp(resolve(tmpdir(), 'testaize-no-node-'));
    const configuredPython = process.env.TESTAIZE_PYTHON || resolve(root, '.venv/Scripts/python.exe');
    const python = execFileSync(configuredPython, ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' }).trim();
    const host = spawn(python, [resolve(root, 'tests/automation_host_fixture.py'), dataRoot], { env: { ...process.env, PATH: '' }, stdio: ['pipe', 'pipe', 'pipe'] });
    host.stderr.resume();
    const lines = createInterface({ input: host.stdout });
    const ready = new Promise((resolveReady, reject) => {
        const timer = setTimeout(() => reject(new Error('No-Node host did not start')), 10000);
        lines.on('line', (line) => { if (line.startsWith('HOST_READY ')) { clearTimeout(timer); resolveReady(line.slice(11)); } });
        host.once('error', (error) => { clearTimeout(timer); reject(error); });
    });
    let browser;
    try {
        const origin = await ready;
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        await page.goto(origin);
        assert.equal(await page.getByRole('link', { name: 'Automação', exact: true }).count(), 0);
        assert.match(await page.locator('.automation-environment-notice').textContent(), /Node.js não encontrado/);
        assert.equal((await page.request.get(origin + '/health')).status(), 200);
        assert.equal((await page.request.get(origin + '/iniciativas/automacao')).status(), 503);
    } finally {
        await browser?.close();
        const stopped = once(host, 'exit');
        host.stdin.end('shutdown\n');
        await stopped;
        await rm(dataRoot, { recursive: true, force: true });
    }
});

test('manual player brand follows dark-theme accents and search fits narrow sidebars', { timeout: 30000 }, async () => {
    const dataRoot = await mkdtemp(resolve(tmpdir(), 'testaize-manual-visual-'));
    const python = process.env.TESTAIZE_PYTHON || resolve(root, '.venv/Scripts/python.exe');
    const host = spawn(python, [resolve(root, 'tests/automation_host_fixture.py'), dataRoot], { env: { ...process.env, TESTAIZE_MANUAL_FIXTURE: '1' }, stdio: ['pipe', 'pipe', 'pipe'] });
    host.stderr.resume();
    let manualId;
    const lines = createInterface({ input: host.stdout });
    const ready = new Promise((resolveReady, reject) => {
        const timer = setTimeout(() => reject(new Error('Manual host did not start')), 10000);
        lines.on('line', (line) => {
            if (line.startsWith('MANUAL_READY ')) manualId = line.slice(13);
            if (line.startsWith('HOST_READY ')) { clearTimeout(timer); resolveReady(line.slice(11)); }
        });
        host.once('error', (error) => { clearTimeout(timer); reject(error); });
    });
    let browser;
    try {
        const origin = await ready;
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
        await page.goto(origin + '/sessao/' + manualId);
        const selectedColors = [];
        for (const accent of ['neutro', 'roxo', 'verde', 'vermelho', 'amarelo']) {
            const colors = await page.evaluate((choice) => {
                document.documentElement.dataset.theme = 'dark'; document.documentElement.dataset.accent = choice;
                const probe = document.createElement('span'); probe.style.color = choice === 'neutro' ? 'var(--ink)' : 'var(--accent)'; document.body.append(probe);
                const expected = getComputedStyle(probe).color; probe.remove();
                return { expected, actual: getComputedStyle(document.querySelector('.topbar .brand > span')).color };
            }, accent);
            assert.equal(colors.actual, colors.expected, accent);
            selectedColors.push(colors.actual);
        }
        assert.equal(new Set(selectedColors).size, 5, 'Every selected color must visibly change the brand.');
        for (const width of [180, 270, 340]) {
            const bounds = await page.evaluate((sidebarWidth) => {
                document.querySelector('.case-sidebar').style.width = sidebarWidth + 'px';
                const wrap = document.querySelector('.search-wrap'); const input = document.querySelector('#case-search');
                return { outer: wrap.getBoundingClientRect().toJSON(), inner: input.getBoundingClientRect().toJSON(), radius: getComputedStyle(input).borderRadius };
            }, width);
            assert.ok(bounds.inner.left >= bounds.outer.left && bounds.inner.right <= bounds.outer.right + 1, JSON.stringify(bounds));
            assert.equal(bounds.radius, '8px');
        }
        await page.evaluate(() => { document.querySelector('.case-sidebar').style.width = ''; document.documentElement.dataset.accent = 'verde'; });
        if (process.env.TESTAIZE_SCREENSHOT) await page.screenshot({ path: process.env.TESTAIZE_SCREENSHOT.replace('.png', '-manual.png'), fullPage: true });
    } finally {
        await browser?.close();
        const stopped = once(host, 'exit'); host.stdin.end('shutdown\n'); await stopped;
        await rm(dataRoot, { recursive: true, force: true });
    }
});
