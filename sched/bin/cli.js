#!/usr/bin/env node
'use strict';

/**
 * sched —— 本地定时任务调度器 CLI。
 *
 * 本文件是 Node.js 入口，只做一件事：把参数透传给 bin/runner.py（Python 实现），
 * 并原样透传 stdout / stderr / 退出码。
 *
 * 用法:
 *   sched <command> [--key value ...]
 *   sched --help
 */

const { spawnSync } = require('child_process');
const path = require('path');

const PKG = require('../package.json');
const RUNNER = path.join(__dirname, 'runner.py');

// 固定使用 python3，不探测解释器路径；缺依赖时由 Python 直接抛出错误
const PYTHON = 'python3';

function main() {
  const argv = process.argv.slice(2);

  // 无参数或 --help/-h 交给 Python 打完整帮助（含所有子命令）
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