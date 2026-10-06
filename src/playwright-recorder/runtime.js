import { createRequire } from 'node:module';
import environment from './environment.cjs';

const entry = process.env.RECORDER_PLAYWRIGHT_MODULE || environment.locatePlaywright().entry;
if (!entry) throw new Error('Playwright Codegen não encontrado no ambiente.');
const playwright = createRequire(import.meta.url)(entry);
export const chromium = playwright.chromium;
export const expect = playwright.expect;
