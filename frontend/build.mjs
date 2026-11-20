import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { compile } from 'tailwindcss';

const output = new URL('../src/testplayer/static/frontend/', import.meta.url);
const stylesheet = await readFile(new URL('progress.css', import.meta.url), 'utf8');
const tailwind = await compile(stylesheet);
await mkdir(output, { recursive: true });
await Promise.all([
  build({
    entryPoints: [fileURLToPath(new URL('progress.jsx', import.meta.url))],
    outfile: fileURLToPath(new URL('progress.js', output)),
    bundle: true,
    jsx: 'automatic',
    minify: true,
    legalComments: 'eof',
    define: { 'process.env.NODE_ENV': '"production"' },
  }),
  writeFile(new URL('progress.css', output), tailwind.build([])),
]);
