// Preloaded in the CLI and its workers: saved specs use the installed Test API.
const Module = require('node:module');
const { join, dirname } = require('node:path');
const resolveFilename = Module._resolveFilename;
Module._resolveFilename = function(request, parent, isMain, options) {
  if (request === '@playwright/test' && process.env.RECORDER_PLAYWRIGHT_MODULE) return process.env.RECORDER_PLAYWRIGHT_MODULE;
  if (request === '@playwright/test/package.json' && process.env.RECORDER_PLAYWRIGHT_MODULE) return join(dirname(process.env.RECORDER_PLAYWRIGHT_MODULE), 'package.json');
  return resolveFilename.call(this, request, parent, isMain, options);
};
