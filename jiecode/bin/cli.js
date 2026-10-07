#!/usr/bin/env node
'use strict';

const { spawnSync } = require('child_process');
const path = require('path');

const PKG = require('../package.json');
const RUNNER = path.join(__dirname, 'runner.py');
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';

function main() {
  const argv = process.argv.slice(2);
  const r = spawnSync(PYTHON, [RUNNER, ...argv], {
    encoding: 'utf8',
    maxBuffer: 50 * 1024 * 1024,
    stdio: ['inherit', 'pipe', 'pipe'],
  });

  if (r.error) {
    console.error(`错误：无法执行 ${PYTHON}：${r.error.message}`);
    process.exit(1);
  }
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
  process.exit(r.status ?? 1);
}

if (process.argv.slice(2).includes('-v') || process.argv.slice(2).includes('--version')) {
  console.log(PKG.version);
  process.exit(0);
}

main();