#!/usr/bin/env node
'use strict';

/**
 * wireguard-easy —— WireGuard 一键部署与接入 CLI。
 *
 * 服务端（Linux, root）：
 *   wireguard-easy install <公网IP或域名> [端口] [网段] [--force]
 *   wireguard-easy add-client <设备名> [隧道IP]
 *   wireguard-easy list-clients
 *   wireguard-easy remove-client <设备名或公钥>
 *   wireguard-easy status [--json]
 *   wireguard-easy qr <设备名>
 *   wireguard-easy conf <设备名>
 *
 * 客户端（Windows）：
 *   wireguard-easy windows [输出目录]
 *
 * 说明：install/add-client/list-clients/remove-client 为对内置 shell 脚本的薄封装，
 *       脚本本体位于 bin/scripts/（与 ielym/wireguard-easy 仓库保持一致）。
 */

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PKG = require('../package.json');
const SCRIPTS = path.join(__dirname, 'scripts');
const ASSETS = path.join(__dirname, '..', 'assets');
const CLIENTS_DIR = '/root/wireguard-clients';
const WG_CONF = '/etc/wireguard/wg0.conf';
const IFACE = 'wg0';
const SOURCE = 'wireguard-easy';

const PROG = 'wireguard-easy';

const HELP = `WireGuard 一键部署与接入（wireguard-easy v${PKG.version}）

用法:
  ${PROG} install <公网IP或域名> [端口=51820] [网段=10.0.0.0/24] [--force]
  ${PROG} add-client <设备名> [隧道IP]
  ${PROG} list-clients
  ${PROG} remove-client <设备名或公钥>
  ${PROG} status [--json]
  ${PROG} qr <设备名>
  ${PROG} conf <设备名>
  ${PROG} windows [输出目录]
  ${PROG} --help | --version

示例:
  sudo ${PROG} install vpn.example.com
  sudo ${PROG} install 43.110.43.207 51820 10.0.0.0/24
  sudo ${PROG} add-client laptop
  sudo ${PROG} add-client phone-xiaomi 10.0.0.4
  ${PROG} status --json
  ${PROG} qr laptop
  ${PROG} windows ./wg-client

说明:
  install / add-client / list-clients / remove-client 需要 root（可用 sudo 运行）。
  客户端配置与二维码生成于 ${CLIENTS_DIR}/。
`;

// --- 通用工具 --------------------------------------------------------------

function die(msg, code = 1) {
  console.error(`错误：${msg}`);
  process.exit(code);
}

/** 文件名安全化：与 add-client.sh 中的 tr 规则一致。 */
function safeName(name) {
  return String(name).replace(/[^a-zA-Z0-9_-]/g, '-');
}

/** 简易参数解析：支持 --k v / --k=v / -k 与位置参数。 */
function parseFlags(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--') {
      positional.push(...argv.slice(i + 1));
      break;
    }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq !== -1) {
        flags[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const key = a.slice(2);
        const next = argv[i + 1];
        if (next !== undefined && !next.startsWith('-')) {
          flags[key] = next;
          i += 1;
        } else {
          flags[key] = true;
        }
      }
    } else if (a.startsWith('-') && a.length > 1) {
      flags[a.slice(1)] = true;
    } else {
      positional.push(a);
    }
  }
  return { positional, flags };
}

function capture(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: 'utf8' });
  if (r.error) return { ok: false, out: '', err: r.error.message };
  return { ok: r.status === 0, out: r.stdout || '', err: r.stderr || '' };
}

function canSudo() {
  if (typeof process.getuid !== 'function' || process.getuid() === 0) return false;
  const r = spawnSync('sudo', ['-n', 'true'], { stdio: 'ignore' });
  return !r.error && r.status === 0;
}

/** 执行内置 shell 脚本；非 root 且免密 sudo 可用时自动提权。 */
function runScript(script, args, extraEnv) {
  const file = path.join(SCRIPTS, script);
  if (!fs.existsSync(file)) die(`缺少脚本 ${file}（安装包不完整）`);
  const env = { ...process.env, ...(extraEnv || {}) };
  let cmd = 'bash';
  let cmdArgs = [file, ...args];
  if (canSudo()) {
    cmd = 'sudo';
    cmdArgs = ['-E', 'bash', file, ...args];
  }
  const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit', env });
  if (r.error) die(`无法执行 ${cmd}：${r.error.message}`);
  return r.status === null ? 1 : r.status;
}

// --- status 相关 -----------------------------------------------------------

function fmtBytes(n) {
  const v = Number(n) || 0;
  if (v <= 0) return '0 B';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let i = 0;
  let x = v;
  while (x >= 1024 && i < units.length - 1) {
    x /= 1024;
    i += 1;
  }
  return `${x.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function fmtAgo(epochSec) {
  const t = Number(epochSec) || 0;
  if (!t) return '从未握手';
  const d = Math.max(0, Math.floor(Date.now() / 1000) - t);
  if (d < 60) return `${d} 秒前`;
  if (d < 3600) return `${Math.floor(d / 60)} 分钟前`;
  if (d < 86400) return `${Math.floor(d / 3600)} 小时前`;
  return `${Math.floor(d / 86400)} 天前`;
}

/** 读取 ${CLIENTS_DIR}/*.pub 建立 公钥 -> 设备名 索引。 */
function loadClientIndex() {
  const index = {};
  let names = [];
  try {
    names = fs.readdirSync(CLIENTS_DIR);
  } catch (_) {
    return index;
  }
  for (const f of names) {
    if (!f.endsWith('.pub')) continue;
    try {
      const pub = fs.readFileSync(path.join(CLIENTS_DIR, f), 'utf8').trim();
      if (pub) index[pub] = f.slice(0, -4);
    } catch (_) { /* 忽略不可读文件 */ }
  }
  return index;
}

function readIfaceAddress() {
  try {
    const conf = fs.readFileSync(WG_CONF, 'utf8');
    const m = conf.match(/^\s*Address\s*=\s*(\S+)/m);
    return m ? m[1] : null;
  } catch (_) {
    return null;
  }
}

function collectStatus() {
  const active = capture('systemctl', ['is-active', `wg-quick@${IFACE}`]);
  const dump = capture('wg', ['show', IFACE, 'dump']);
  const index = loadClientIndex();
  const clients = Object.values(index).sort().map((name) => ({
    name,
    conf: path.join(CLIENTS_DIR, `${name}.conf`),
    has_conf: fs.existsSync(path.join(CLIENTS_DIR, `${name}.conf`)),
    has_qr: fs.existsSync(path.join(CLIENTS_DIR, `${name}.png`)),
  }));

  let iface = null;
  const peers = [];
  if (dump.ok && dump.out.trim()) {
    const lines = dump.out.split('\n').filter((l) => l.trim());
    const head = lines[0].split('\t');
    iface = {
      name: IFACE,
      public_key: head[1] || null,
      listen_port: Number(head[2]) || null,
      address: readIfaceAddress(),
      active: active.ok,
    };
    for (const line of lines.slice(1)) {
      const [pub, , endpoint, allowed, hs, rx, tx, ka] = line.split('\t');
      peers.push({
        name: index[pub] || null,
        public_key: pub || null,
        endpoint: endpoint && endpoint !== '(none)' ? endpoint : null,
        allowed_ips: allowed ? allowed.split(',').filter(Boolean) : [],
        latest_handshake: Number(hs) || 0,
        latest_handshake_ago: fmtAgo(hs),
        transfer_rx: Number(rx) || 0,
        transfer_tx: Number(tx) || 0,
        persistent_keepalive: Number(ka) || 0,
      });
    }
  }

  return {
    source: SOURCE,
    captured_at: new Date().toISOString(),
    interface: iface,
    service_active: active.ok,
    peers,
    clients,
  };
}

function cmdStatus(argv) {
  const { flags } = parseFlags(argv);
  const st = collectStatus();

  if (flags.json) {
    console.log(JSON.stringify({ ...st, count: st.peers.length }, null, 2));
    return 0;
  }

  console.log(`接口 ${IFACE}：${st.service_active ? '运行中' : '未运行'}`);
  if (st.interface) {
    console.log(`  地址    : ${st.interface.address || '未知'}`);
    console.log(`  监听    : UDP ${st.interface.listen_port || '未知'}`);
    console.log(`  服务公钥: ${st.interface.public_key || '未知'}`);
  } else if (!st.service_active) {
    console.log('  （wg0 未运行或非 root 无权读取，可 sudo 重试）');
  }

  console.log(`\n设备 (${st.peers.length}):`);
  if (!st.peers.length) {
    console.log('  （无 peer，先运行: sudo ' + PROG + ' add-client <设备名>）');
  }
  for (const p of st.peers) {
    const label = (p.name || p.public_key || '').padEnd(18);
    const ip = (p.allowed_ips[0] || '-').padEnd(14);
    console.log(`  ${label}${ip}${p.latest_handshake_ago}  ↓${fmtBytes(p.transfer_rx)} / ↑${fmtBytes(p.transfer_tx)}`);
  }

  const missing = st.clients.filter((c) => !c.has_conf);
  console.log(`\n客户端文件 (${st.clients.length}): ${CLIENTS_DIR}/`);
  if (missing.length) console.log(`  注意：${missing.map((c) => c.name).join(', ')} 缺少 .conf`);
  return 0;
}

// --- qr / conf -------------------------------------------------------------

/** 解析设备名对应的客户端文件路径（先按安全化名，再回退原名）。 */
function clientFile(name, ext) {
  const candidates = [path.join(CLIENTS_DIR, `${safeName(name)}.${ext}`), path.join(CLIENTS_DIR, `${name}.${ext}`)];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

function cmdQr(argv) {
  const { positional } = parseFlags(argv);
  const name = positional[0];
  if (!name) die(`用法: ${PROG} qr <设备名>`);
  const conf = clientFile(name, 'conf');
  if (!conf) die(`找不到 ${CLIENTS_DIR}/${safeName(name)}.conf，请先运行: sudo ${PROG} add-client ${name}`);
  const png = clientFile(name, 'png');
  if (png) console.log(`二维码图片: ${png}`);
  const r = spawnSync('qrencode', ['-t', 'ANSIUTF8'], { input: fs.readFileSync(conf) });
  if (!r.error && r.status === 0 && r.stdout) {
    process.stdout.write(r.stdout);
  } else {
    console.log('（未安装 qrencode，无法在终端渲染二维码；可使用上方图片或用 WireGuard App 从文件导入 .conf）');
  }
  return 0;
}

function cmdConf(argv) {
  const { positional } = parseFlags(argv);
  const name = positional[0];
  if (!name) die(`用法: ${PROG} conf <设备名>`);
  const conf = clientFile(name, 'conf');
  if (!conf) die(`找不到 ${CLIENTS_DIR}/${safeName(name)}.conf，请先运行: sudo ${PROG} add-client ${name}`);
  process.stdout.write(fs.readFileSync(conf));
  return 0;
}

// --- windows ---------------------------------------------------------------

function cmdWindows(argv) {
  const { positional } = parseFlags(argv);
  const outDir = positional[0] || process.cwd();
  fs.mkdirSync(outDir, { recursive: true });
  const files = fs.readdirSync(path.join(ASSETS, 'windows'));
  for (const f of files) {
    fs.copyFileSync(path.join(ASSETS, 'windows', f), path.join(outDir, f));
  }
  console.log(`✅ 已导出 Windows 一键连接脚本到: ${path.resolve(outDir)}`);
  for (const f of files) console.log(`   - ${f}`);
  console.log('');
  console.log('接下来:');
  console.log(`  1) 服务器执行 sudo ${PROG} add-client <设备名>，取回 ${CLIENTS_DIR}/<设备名>.conf`);
  console.log('  2) 把该 .conf 重命名为 wireguard-client.conf 放到上述目录');
  console.log('  3) 右键「以管理员身份运行」onekey-connect.bat（自动装客户端 → 导入 → 连接）');
  return 0;
}

// --- 入口 ------------------------------------------------------------------

const COMMANDS = {
  install: (argv) => {
    const { positional, flags } = parseFlags(argv);
    const endpoint = positional[0] || flags.endpoint;
    if (!endpoint) die(`用法: sudo ${PROG} install <公网IP或域名> [端口] [网段] [--force]`);
    const port = String(positional[1] || flags.port || '51820');
    const subnet = String(positional[2] || flags.subnet || '10.0.0.0/24');
    const env = {};
    if (flags.force) env.FORCE = '1';
    return runScript('install.sh', [String(endpoint), port, subnet], env);
  },
  'add-client': (argv) => {
    const { positional, flags } = parseFlags(argv);
    const name = positional[0] || flags.name;
    if (!name) die(`用法: sudo ${PROG} add-client <设备名> [隧道IP]`);
    const ip = positional[1] || flags.ip;
    return runScript('add-client.sh', [String(name), ...(ip ? [String(ip)] : [])]);
  },
  'list-clients': (argv) => {
    parseFlags(argv);
    return runScript('list-clients.sh', []);
  },
  'remove-client': (argv) => {
    const { positional, flags } = parseFlags(argv);
    const target = positional[0] || flags.target;
    if (!target) die(`用法: sudo ${PROG} remove-client <设备名或公钥>`);
    return runScript('remove-client.sh', [String(target)]);
  },
  status: cmdStatus,
  qr: cmdQr,
  conf: cmdConf,
  windows: cmdWindows,
};

function main() {
  const argv = process.argv.slice(2);
  const first = argv[0];

  if (!first || first === '-h' || first === '--help' || first === 'help') {
    process.stdout.write(HELP);
    return 0;
  }
  if (first === '-v' || first === '--version') {
    console.log(PKG.version);
    return 0;
  }

  const handler = COMMANDS[first];
  if (!handler) {
    console.error(`错误：未知命令 "${first}"`);
    console.error(`运行 ${PROG} --help 查看可用命令。`);
    return 1;
  }
  return handler(argv.slice(1));
}

process.exit(main());