#!/usr/bin/env node
'use strict';

/**
 * openrouter —— OpenRouter 模型目录抓取 CLI（输出解析后的结构化 JSON）。
 *
 * 用法:
 *   openrouter [--limit N]
 *   openrouter --help
 */

const { spawnSync } = require('child_process');
const path = require('path');

const PKG = require('../package.json');
const RUNNER = path.join(__dirname, 'runner.py');
const PYTHON = 'python3';

function main() {
  const argv = process.argv.slice(2);

  if (argv.includes('-v') || argv.includes('--version')) {
    console.log(PKG.version);
    return;
  }

  const r = spawnSync(PYTHON, [RUNNER, ...argv], {
    encoding: 'utf8',
    maxBuffer: 50 * 1024 * 1024,
    env: { ...process.env },
  });

  if (r.error) {
    console.error(`错误：无法执行 ${PYTHON}：${r.error.message}`);
    process.exit(1);
  }
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
  process.exit(r.status ?? 1);
}

main();