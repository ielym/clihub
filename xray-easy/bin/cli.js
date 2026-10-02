#!/usr/bin/env node
/**
 * xray-easy :: Xray VLESS+Reality 一键部署与接入 CLI
 * 用法: xray-easy <命令> [参数]
 * 需要 root 的命令会调用 sudo 提示；全部命令转发到 bin/scripts/ 下的 bash 脚本。
 */
'use strict';

const { execFileSync } = require('child_process');
const path = require('path');

const SCRIPTS = path.join(__dirname, 'scripts');
const BIN = name => path.join(SCRIPTS, `${name}.sh`);

const HELP = `xray-easy :: Xray VLESS+Reality 一键部署与接入

用法:
  sudo xray-easy install [--dest 站点:端口] [--port 端口] [--force]
        安装 Xray + 生成密钥/UUID + 写 Reality 配置 + 启动（幂等）
  sudo xray-easy link <公网IP或域名> [--qr]
        生成 vless:// 链接（--qr 同时输出二维码 PNG）
  sudo xray-easy change-dest <站点[:端口]>
        更换伪装站点（换后客户端 sni 需同步更新）
  sudo xray-easy status [--json]
        查看服务/端口/伪装站点/连接/错误日志
  sudo xray-easy restart | start | stop
        服务管理
  sudo xray-easy log [行数]
        查看 access/error 日志

客户端（手机）接入: 安装 v2rayNG → 复制导入 vless 链接或扫码 → 连接。
文档: 见仓库 SKILL.md 与 references/（安装/使用/排障/注意事项）。`;

function run(cmd, args) {
  try {
    const out = execFileSync('bash', [BIN(cmd), ...args], { stdio: 'inherit' });
    return out;
  } catch (e) {
    process.exit(e.status || 1);
  }
}

const [,, cmd, ...rest] = process.argv;
if (!cmd || cmd === '-h' || cmd === '--help' || cmd === 'help') {
  console.log(HELP);
  process.exit(0);
}

const MAP = {
  install:      'install',
  link:         'link',
  qr:           'link',
  'change-dest':'change-dest',
  status:       'status',
  restart:      'service',
  start:        'service',
  stop:         'service',
  log:          'service',
};

const script = MAP[cmd];
if (!script) { console.error(`❌ 未知命令: ${cmd}\n`); console.log(HELP); process.exit(1); }

if (cmd === 'restart' || cmd === 'start' || cmd === 'stop') run('service', [cmd]);
else if (cmd === 'log') run('service', ['log', ...(rest[0] ? [rest[0]] : ['30'])]);
else if (cmd === 'qr') run('link', [rest[0], '--qr']);
else run(script, rest);
