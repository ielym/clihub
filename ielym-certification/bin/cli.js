#!/usr/bin/env node
'use strict';

/**
 * ielym-certification —— 统一的权限凭证获取 CLI。
 *
 * Node.js 入口，负责：
 *   1. 用 python3 调用 bin/runner.py 执行具体操作
 *   2. 透传输出与退出码
 *
 * 用法:
 *   ielym-certification providers
 *   ielym-certification <provider> [参数...]
 *   ielym-certification --help
 */

const { spawnSync } = require('child_process');
const path = require('path');

// runner.py 与本文件同目录
const RUNNER = path.join(__dirname, 'runner.py');

// 固定使用 python3，不探测也不指定解释器路径；缺依赖时由 Python 直接抛出错误
const PYTHON = 'python3';

function main() {
  const argv = process.argv.slice(2);

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