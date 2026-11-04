const { createRequire } = require('node:module');
const { existsSync } = require('node:fs');
const { dirname, join, delimiter } = require('node:path');

function locatePlaywright() {
  const candidates = [process.cwd(), __dirname, join(__dirname, '..', '..'), dirname(process.execPath)];
  for (const value of [process.env.NODE_PATH, process.env.TESTAIZE_PLAYWRIGHT_PATH]) {
    if (value) candidates.push(...value.split(delimiter));
  }
  if (process.env.APPDATA) candidates.push(join(process.env.APPDATA, 'npm', 'node_modules'));
  if (process.env.npm_config_prefix) candidates.push(join(process.env.npm_config_prefix, 'node_modules'));
  for (const directory of (process.env.PATH || '').split(delimiter)) {
    if (['playwright', 'playwright.cmd', 'playwright.ps1'].some((command) => existsSync(join(directory, command)))) candidates.push(join(directory, 'node_modules'));
  }
  candidates.push(join(dirname(process.execPath), 'node_modules'), '/usr/local/lib/node_modules', '/usr/lib/node_modules');
  const loader = createRequire(__filename);
  for (const name of ['@playwright/test', 'playwright']) {
    try {
      const metadata = loader.resolve(name + '/package.json', { paths: candidates });
      const packageRoot = dirname(metadata);
      const version = loader(metadata).version;
      if (version !== '1.62.1') continue;
      const entry = name === 'playwright' ? loader.resolve('playwright/test', { paths: [packageRoot] }) : loader.resolve(name, { paths: candidates });
      const runtime = loader(entry);
      if (!existsSync(join(packageRoot, 'cli.js')) || !runtime.chromium || !runtime.expect) continue;
      if (!existsSync(runtime.chromium.executablePath())) return { available: false, message: 'Chromium do Playwright não encontrado. Instale-o no ambiente e reinicie o aplicativo.' };
      return { available: true, entry, version };
    } catch { /* Probe the next existing installation, never install packages here. */ }
  }
  return { available: false, message: 'Playwright Codegen 1.62.1 não encontrado no ambiente. Automação indisponível até a próxima abertura.' };
}

module.exports = { locatePlaywright };
if (require.main === module) {
  const major = Number(process.versions.node.split('.')[0]);
  console.log(JSON.stringify(major >= 20 ? locatePlaywright() : { available: false, message: 'Automação requer Node.js 20 ou superior.' }));
}
