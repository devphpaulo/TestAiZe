import assert from 'node:assert/strict';
import { test } from 'node:test';
import { chromium } from '../runtime.js';
import { PlaywrightRecorderAdapter } from '../playwright-recorder-adapter.js';

test('email identifiers and passwords become env references before emission', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.setContent('<input type="email" id="mail"><input id="email"><label>E-mail <input id="labelled"></label><input name="login_email" id="named"><input type="password" id="password"><input id="plain">');
    let sink;
    const fake = { _enableRecorder: async (_options, value) => { sink = value; } };
    const updates = [];
    const adapter = new PlaywrightRecorderAdapter(fake, (code) => updates.push(code));
    await adapter.enable();
    for (const selector of ['#mail', '#email', '#labelled', '#named']) {
      sink.actionAdded(page, { action: { name: 'fill', selector } }, `await page.locator('${selector}').fill('canary@example.test');`);
    }
    sink.actionAdded(page, { action: { name: 'fill', selector: '#password' } }, "await page.locator('#password').fill('canary-secret');");
    sink.actionAdded(page, { action: { name: 'fill', selector: '#plain' } }, "await page.locator('#plain').fill('Normal');");
    await adapter.whenIdle();
    assert.equal(updates.some((code) => code.includes('canary@example.test') || code.includes('canary-secret')), false);
    assert.equal(updates.at(-1).match(/process.env.PLAYWRIGHT_EMAIL/g).length, 4);
    assert.match(updates.at(-1), /process.env.PLAYWRIGHT_PASSWORD/);
    assert.match(updates.at(-1), /fill\('Normal'\)/);
    await adapter.close();
    await context.close();
  } finally { await browser.close(); }
});
