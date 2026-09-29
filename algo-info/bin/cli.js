#!/usr/bin/env node
'use strict';

/**
 * algo-info —— 算法信息数据源聚合系统 CLI。
 *
 * 本脚本是 Node 封装层，实际执行 Python 项目（algo_info_aggregator）。
 *
 * 用法:
 *   algo-info config set <项目目录>          记录 Python 项目路径（写入 ~/.algo-info.json）
 *   algo-info config show                    查看当前配置
 *   algo-info fetch <source> [--limit N]     抓取单个数据源
 *   algo-info fetch-all [--limit N]          抓取所有数据源
 *   algo-info test                            运行逐项测试
 *   algo-info serve [--port 8000]            启动查询 API
 *   algo-info stats                           查看数据统计
 *   algo-info sources                         列出所有数据源
 *   algo-info search <query> [--limit N]     搜索论文
 *   algo-info repos  <query> [--limit N]     搜索代码仓库
 *   algo-info models <query> [--limit N]     搜索模型
 *
 * 仅用 Node 内置模块。
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

const HOME = os.homedir();
const CONFIG_PATH = path.join(HOME, '.algo-info.json');

// ── 配置 ────────────────────────────────────

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
  } catch {
    return {};
  }
}

function writeConfig(cfg) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + '\n');
}

function getProjectDir() {
  // 优先级: 环境变量 > 配置文件 > 默认值
  return process.env.ALGO_INFO_HOME || readConfig().project_dir || null;
}

// ── 定位 Python 解释器 ──────────────────────

function findPython(projectDir) {
  if (!projectDir) return null;
  // 候选路径列表（按优先级）
  const candidates = [
    path.join(projectDir, '.venv', 'Scripts', 'python.exe'),      // Windows venv 在项目根
    path.join(projectDir, '.venv', 'bin', 'python'),               // Unix venv 在项目根
    path.join(projectDir, 'algo_info_aggregator', '.venv', 'Scripts', 'python.exe'), // venv 在包内
    path.join(projectDir, 'algo_info_aggregator', '.venv', 'bin', 'python'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  // 回退到系统 python
  return 'python';
}

// ── 调用 Python CLI ─────────────────────────

function callPython(projectDir, args) {
  const python = findPython(projectDir);
  if (!python) {
    console.error('未找到 Python 项目路径。请先运行: algo-info config set <项目目录>');
    process.exit(1);
  }
  const fullArgs = ['-m', 'algo_info_aggregator.cli', ...args];
  const result = spawnSync(python, fullArgs, {
    cwd: projectDir,
    stdio: 'inherit',
    env: { ...process.env },
  });
  process.exit(result.status ?? 1);
}

// ── 子命令 ──────────────────────────────────

function cmdConfig(action, value) {
  if (action === 'set') {
    if (!value) { console.error('用法: algo-info config set <项目目录>'); process.exit(1); }
    const dir = path.resolve(value);
    if (!fs.existsSync(dir)) { console.error(`目录不存在: ${dir}`); process.exit(1); }
    // 校验目录下有 algo_info_aggregator 包
    const pkgInit = path.join(dir, 'algo_info_aggregator', '__init__.py');
    if (!fs.existsSync(pkgInit)) {
      console.error(`未在 ${dir} 下找到 algo_info_aggregator 包`);
      process.exit(1);
    }
    writeConfig({ project_dir: dir });
    console.log(`已设置项目目录: ${dir}`);
    const py = findPython(dir);
    console.log(`Python: ${py}`);
    return;
  }
  if (action === 'show') {
    const cfg = readConfig();
    console.log(JSON.stringify(cfg, null, 2) || '（未配置）');
    return;
  }
  console.error('用法: algo-info config <set|show> [目录]');
  process.exit(1);
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0) {
    printHelp();
    process.exit(0);
  }

  const cmd = argv[0];

  // config 子命令不依赖项目目录
  if (cmd === 'config') {
    cmdConfig(argv[1], argv[2]);
    return;
  }

  if (cmd === '--help' || cmd === '-h' || cmd === 'help') {
    printHelp();
    return;
  }

  const projectDir = getProjectDir();
  if (!projectDir) {
    console.error('未配置 Python 项目路径。请先运行: algo-info config set <项目目录>');
    console.error('（环境变量 ALGO_INFO_HOME 也可指定）');
    process.exit(1);
  }

  // 其余命令透传给 Python CLI
  callPython(projectDir, argv);
}

function printHelp() {
  console.log(`algo-info —— 算法信息数据源聚合系统 CLI

配置:
  algo-info config set <项目目录>    记录 Python 项目路径
  algo-info config show              查看当前配置

数据抓取:
  algo-info fetch <source> [--limit N] [--params JSON]
  algo-info fetch-all [--limit N]

查询:
  algo-info stats                           数据统计
  algo-info sources                         数据源列表
  algo-info search <query> [--limit N]      搜索论文
  algo-info repos  <query> [--limit N]      搜索代码仓库
  algo-info models <query> [--limit N]      搜索模型

测试 & 服务:
  algo-info test                            运行逐项测试
  algo-info serve [--port 8000]             启动查询 API

数据源: arxiv, github_trending, openreview, artificial_analysis,
        openrouter, acl_anthology, pmlr, cvf, dblp, huggingface_papers

环境变量: ALGO_INFO_HOME=<项目目录>  可替代 config set
`);
}

main();
