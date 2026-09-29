#!/usr/bin/env node
'use strict';

/**
 * em-crawler —— 东方财富全量采集 CLI。
 *
 * 本文件是 Node.js 入口，负责：
 *   1. 解析命令行参数
 *   2. 定位 Python 解释器与爬虫根目录
 *   3. 调用 bin/runner.py 执行实际采集
 *   4. 透传 JSON 输出到 stdout
 *
 * 用法:
 *   em-crawler <command> [--key value ...]
 *   em-crawler list
 *   em-crawler --help
 */

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const os = require('os');

const PKG = require('../package.json');

// runner.py 与本文件同目录
const RUNNER = path.join(__dirname, 'runner.py');

function findPython() {
  // 1. 环境变量优先
  const envPy = process.env.EM_CRAWLER_PYTHON;
  if (envPy && fs.existsSync(envPy)) return envPy;

  // 2. 尝试常见名称
  const candidates = ['python', 'python3', 'py'];
  for (const c of candidates) {
    const r = spawnSync(c, ['-c', 'import sys; print(sys.executable)'], { encoding: 'utf8' });
    if (r.status === 0 && r.stdout.trim()) {
      return r.stdout.trim();
    }
  }
  return null;
}

function main() {
  const argv = process.argv.slice(2);

  if (argv.length === 0 || argv.includes('-h') || argv.includes('--help')) {
    const py = findPython();
    if (py) {
      const r = spawnSync(py, [RUNNER, '--help'], { encoding: 'utf8' });
      console.log(r.stdout || r.stderr);
    } else {
      console.log('em-crawler —— 东方财富全量采集 CLI');
      console.log('用法: em-crawler <command> [--key value ...]');
      console.log('      em-crawler list');
      console.log('未找到 Python，请设置 EM_CRAWLER_PYTHON 环境变量。');
    }
    return;
  }

  if (argv.includes('-v') || argv.includes('--version')) {
    console.log(PKG.version);
    return;
  }

  const py = findPython();
  if (!py) {
    console.error('错误：未找到 Python 解释器。');
    console.error('请设置环境变量 EM_CRAWLER_PYTHON 指向 Python 可执行文件路径。');
    process.exit(1);
  }

  // 把所有参数透传给 runner.py
  const r = spawnSync(py, [RUNNER, ...argv], {
    encoding: 'utf8',
    maxBuffer: 50 * 1024 * 1024, // 50MB，财务/行情数据可能较大
    stdio: ['inherit', 'pipe', 'pipe'],
  });

  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);

  process.exit(r.status || 0);
}

main();
