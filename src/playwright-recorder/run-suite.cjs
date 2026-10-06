const { dirname, join } = require('node:path');

const entry = process.env.RECORDER_PLAYWRIGHT_MODULE;
const config = process.argv[2];
if (!entry || !config) {
  console.error('Configuração do runner indisponível.');
  process.exit(1);
}
const cli = join(dirname(entry), 'cli.js');
process.argv = [process.execPath, cli, 'test', '--config', config];

// The ownership pipe stays open while Python is alive; EOF cleans up an orphan.
process.stdin.resume();
process.stdin.once('end', () => process.exit(1));
require(cli);
