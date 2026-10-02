#!/usr/bin/env node
'use strict';

/**
 * ip-tunnel —— 快代理隧道代理（IP 隧道）CLI。
 *
 * Node.js 薄封装，负责：
 *   1. 解析命令行（透传给 runner.py）
 *   2. 用 python3 调用 bin/runner.py 执行
 *   3. 透传 stdout / stderr / 退出码
 *
 * 用法:
 *   ip-tunnel <command> [options]       # 见 --help
 *   ip-tunnel --help
 */

const { spawnSync } = require('child_process');
const path = require('path');

const PKG = require('../package.json');

// runner.py 与本文件同目录
const RUNNER = path.join(__dirname, 'runner.py');

// 固定使用 python3
const PYTHON = 'python3';

function main() {
  const argv = process.argv.slice(2);

  if (argv.includes('-v') || argv.includes('--version')) {
    console.log(PKG.version);
    return 0;
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