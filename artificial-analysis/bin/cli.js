#!/usr/bin/env node
'use strict';

/**
 * artificial-analysis —— ArtificialAnalysis 模型评测原始抓取 CLI。
 *
 * Node.js 入口，负责：
 *   1. 解析命令行参数
 *   2. 用 python3 调用 bin/runner.py 执行抓取
 *   3. 透传 JSON 输出与退出码
 *
 * 用法:
 *   artificial-analysis [--modality M] [--limit N]
 *   artificial-analysis --help
 */

const { spawnSync } = require('child_process');
const path = require('path');

const PKG = require('../package.json');

// runner.py 与本文件同目录
const RUNNER = path.join(__dirname, 'runner.py');

// 固定使用 python3，不探测也不指定解释器路径
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