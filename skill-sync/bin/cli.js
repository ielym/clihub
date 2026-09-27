#!/usr/bin/env node
'use strict';

/**
 * skill-sync —— 一份 Skill 源仓库，分发到本机所有 AI 工具。
 *
 * 用法:
 *   skill-sync status
 *   skill-sync link [--force] [--dir <源仓库>]
 *   skill-sync unlink <tool>
 *   skill-sync install <name>      用 skillhub 装技能，自动补 --dir
 *   skill-sync pull / push ["msg"]
 *
 * 零依赖，仅用 Node 内置模块。
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

const IS_WIN = process.platform === 'win32';
const HOME = os.homedir();
const CONFIG_PATH = path.join(HOME, '.skill-sync.json');

const TARGETS = {
  workbuddy: '.workbuddy/skills',
  claude: '.claude/skills',
  cursor: '.cursor/skills',
  windsurf: '.codeium/windsurf/skills',
  codex: '.codex/skills',
  gemini: '.gemini/skills',
  antigravity: '.gemini/antigravity/skills',
  qoderwork: '.qoderwork/skills',
};

const DEFAULT_HUB = path.join(HOME, '.workbuddy', 'skills');

// 社区 / 第三方 skills：源码不进 git，只把来源声明在清单里
const EXT_MANIFEST = path.join('skill-sync', 'references', 'external-skills.json');
const EXT_DIR = 'external_skills';

// ── 工具函数 ────────────────────────────────

function pad(s, n) {
  // 中文按两个宽度算，保证终端对齐
  let w = 0;
  for (const ch of String(s)) w += /[\u4e00-\u9fa5]/.test(ch) ? 2 : 1;
  return String(s) + ' '.repeat(Math.max(0, n - w));
}

function ts() {
  const d = new Date();
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function real(p) {
  try { return fs.realpathSync(p); } catch { return p; }
}

function isSymlink(p) {
  try { return fs.lstatSync(p).isSymbolicLink(); } catch { return false; }
}

function resolveSource(dirArg) {
  if (dirArg) return path.resolve(dirArg);
  if (process.env.SKILLS_HUB) return path.resolve(process.env.SKILLS_HUB);
  try {
    const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    if (cfg && cfg.hub) return path.resolve(cfg.hub);
  } catch { /* 还没配置过 */ }
  return DEFAULT_HUB;
}

function saveSource(p) {
  try { fs.writeFileSync(CONFIG_PATH, JSON.stringify({ hub: p }, null, 2) + '\n'); } catch { /* 只读环境就算了 */ }
}

function toolInstalled(rel) {
  return fs.existsSync(path.join(HOME, path.dirname(rel)));
}

function isLinked(target, source) {
  if (!fs.existsSync(target)) return false;
  return real(target) === real(source) && path.resolve(target) !== path.resolve(source);
}

function createJunction(target, source) {
  // Windows 用 junction（免管理员），Unix 用目录符号链接
  const type = IS_WIN ? 'junction' : 'dir';
  try {
    fs.symlinkSync(source, target, type);
    return null;
  } catch (e) {
    const msg = e.message || String(e);
    if (/EPERM|EACCES|privilege/i.test(msg)) return '失败：需要管理员权限，改用管理员终端重试';
    if (/EEXIST/i.test(msg)) return '失败：目标已存在（加 --force 先备份）';
    return `失败：${msg}`;
  }
}

function removeLink(target) {
  // junction / 目录链接用 rmdir 删，只删链接本身，不碰源内容
  try { fs.rmdirSync(target); return; } catch { /* 可能是文件符号链接 */ }
  try { fs.unlinkSync(target); } catch { /* 忽略 */ }
}

function linkOne(target, source, force) {
  if (isLinked(target, source)) return '已链接';

  if (fs.existsSync(target) || isSymlink(target)) {
    let entries = [];
    try { entries = fs.readdirSync(target); } catch { /* ignore */ }
    if (entries.length > 0) {
      if (!force) return '跳过：目录非空（加 --force 先备份再链接）';
      const backup = `${target}.bak-${ts()}`;
      fs.renameSync(target, backup);
      console.log(`    已备份原目录 -> ${backup}`);
    } else {
      removeLink(target);
    }
  }

  fs.mkdirSync(path.dirname(target), { recursive: true });
  return createJunction(target, source) || '已建立链接';
}

/**
 * 识别源仓库是"家族包"还是"扁平 skills 目录"。
 * 家族包：<src>/skills/<name>/SKILL.md
 * 扁平：<src>/<name>/SKILL.md
 */
function hasSkillMd(dir) {
  try { return fs.existsSync(path.join(dir, 'SKILL.md')); } catch { return false; }
}

function subdirsWithSkill(dir) {
  try {
    return fs.readdirSync(dir)
      .filter((n) => !n.startsWith('.') && n !== 'node_modules')
      .map((n) => ({ name: n, src: path.join(dir, n) }))
      .filter((it) => {
        try { return fs.statSync(it.src).isDirectory() && hasSkillMd(it.src); } catch { return false; }
      });
  } catch { return []; }
}

/**
 * 识别源仓库的三种形态：
 *   family   —— <src>/skills/<name>/SKILL.md（旧式家族包）
 *   packages —— <src>/<pkg>/SKILL.md（容器里有多个 skill 包，推荐）
 *   plain    —— 源目录本身就是 skills 目录，整体链接
 */
function extDir(source) {
  return path.join(source, EXT_DIR);
}

function listSkillItems(source) {
  // 自建（git 管理）+ 社区（external_skills，不进 git）合并成一个待链接列表
  const famDir = path.join(source, 'skills');
  try {
    if (fs.statSync(famDir).isDirectory()) {
      const items = subdirsWithSkill(famDir);
      if (items.length > 0) return { mode: 'family', items: items.concat(subdirsWithSkill(extDir(source))) };
    }
  } catch { /* 不是家族结构 */ }

  const own = subdirsWithSkill(source);
  const ext = subdirsWithSkill(extDir(source)).filter((e) => !own.some((o) => o.name === e.name));
  const items = own.concat(ext);
  if (items.length > 0) return { mode: 'packages', items };
  return { mode: 'plain', items: null };
}

function loadManifest(source) {
  try {
    const m = JSON.parse(fs.readFileSync(path.join(source, EXT_MANIFEST), 'utf8'));
    return Array.isArray(m.skills) ? m : { skills: [] };
  } catch { return { skills: [] }; }
}

function saveManifest(source, manifest) {
  fs.writeFileSync(path.join(source, EXT_MANIFEST), JSON.stringify(manifest, null, 2) + '\n');
}

function describeMode(mode, items) {
  if (mode === 'family') return `家族包 skills/（${items.length} 个 skill）`;
  if (mode === 'packages') return `多技能包容器（${items.length} 个：${items.map((i) => i.name).join(', ')}）`;
  return '扁平 skills 目录（整体链接）';
}

// ── 子命令 ──────────────────────────────────

function cmdStatus(source) {
  const { mode, items } = listSkillItems(source);
  console.log(`Skill 源仓库：${source}`);
  console.log(`模式：${describeMode(mode, items)}\n`);

  if (mode === 'family' || mode === 'packages') {
    console.log(`${pad('工具', 12)}${pad('Skill', 22)}状态`);
    console.log('-'.repeat(58));
    for (const [tool, rel] of Object.entries(TARGETS)) {
      const root = path.join(HOME, rel);
      if (!toolInstalled(rel)) { console.log(`${pad(tool, 12)}${pad('-', 22)}未安装`); continue; }
      for (const it of items) {
        const t = path.join(root, it.name);
        const st = isLinked(t, it.src) ? '已链接' : fs.existsSync(t) ? '独立目录' : '未链接';
        console.log(`${pad(tool, 12)}${pad(it.name, 22)}${st}`);
      }
    }
    return;
  }

  console.log(`${pad('工具', 14)}${pad('状态', 12)}路径`);
  console.log('-'.repeat(74));
  for (const [tool, rel] of Object.entries(TARGETS)) {
    const target = path.join(HOME, rel);
    let state;
    if (!toolInstalled(rel)) state = '未安装';
    else if (isLinked(target, source)) state = '已链接';
    else if (fs.existsSync(target)) state = '独立目录';
    else state = '可链接';
    console.log(`${pad(tool, 14)}${pad(state, 12)}${target}`);
  }
}

function cmdLink(source, force) {
  if (!fs.existsSync(source)) {
    console.error(`源仓库不存在：${source}\n用 --dir 指定，或先 git clone 到 ${DEFAULT_HUB}`);
    process.exit(1);
  }
  saveSource(source);
  const { mode, items } = listSkillItems(source);
  console.log(`Skill 源仓库：${source}`);
  console.log(`模式：${describeMode(mode, items)}\n`);

  for (const [tool, rel] of Object.entries(TARGETS)) {
    if (!toolInstalled(rel)) continue;
    const root = path.join(HOME, rel);
    if (path.resolve(root) === path.resolve(source)) {
      console.log(`  ${pad(tool, 12)}本仓库就在此路径，无需链接`);
      continue;
    }
    if (mode === 'family' || mode === 'packages') {
      fs.mkdirSync(root, { recursive: true });
      for (const it of items) {
        console.log(`  ${pad(tool, 12)}${pad(it.name, 22)}${linkOne(path.join(root, it.name), it.src, force)}`);
      }
    } else {
      console.log(`  ${pad(tool, 14)}${linkOne(root, source, force)}`);
    }
  }
  console.log('\n完成。改一处，所有工具立即生效。');
}

function cmdUnlink(source, tool) {
  const rel = TARGETS[tool];
  if (!rel) { console.error(`未知工具：${tool}（可选：${Object.keys(TARGETS).join(', ')}）`); process.exit(1); }
  const root = path.join(HOME, rel);
  const { mode, items } = listSkillItems(source);

  let removed = 0;
  if (mode === 'family' || mode === 'packages') {
    for (const it of items) {
      const t = path.join(root, it.name);
      if (isLinked(t, it.src)) { removeLink(t); removed++; }
    }
  } else if (isLinked(root, source)) {
    removeLink(root); removed++;
  }

  console.log(removed > 0
    ? `${tool} 已解除 ${removed} 个链接（源仓库文件未动）`
    : `${tool} 当前没有指向源仓库的链接，未改动`);
}

function cmdInstall(source, name) {
  const args = ['install', name, '--dir', source];
  console.log(`执行：skillhub ${args.join(' ')}`);
  const r = spawnSync('skillhub', args, { stdio: 'inherit', shell: IS_WIN });
  if (r.status !== 0) {
    console.log('\n若提示找不到 skillhub，先装 CLI：');
    console.log('  curl -fsSL https://skillhub.cn/install/install.sh | bash -s -- --cli-only');
    process.exit(r.status == null ? 1 : r.status);
  }
  console.log('\n已装入源仓库，其它工具运行 skill-sync link 即可同步。');
}

function git(source, args) {
  const r = spawnSync('git', args, { cwd: source, stdio: 'inherit' });
  if (r.error) {
    console.error(`无法运行 git：${r.error.message}`);
    return null;
  }
  return r.status;
}

function cmdPull(source) {
  process.exit(git(source, ['pull', '--rebase', '--autostash']) === 0 ? 0 : 1);
}

function cmdPush(source, message) {
  const msg = message || 'update skills';
  if (git(source, ['add', '-A']) !== 0) process.exit(1);
  const commit = git(source, ['commit', '-m', msg]);
  if (commit === null) process.exit(1);
  if (commit !== 0) {
    console.log('没有需要提交的改动，或提交失败。');
    return;
  }
  process.exit(git(source, ['push']) === 0 ? 0 : 1);
}

function installOne(s, targetDir) {
  // clawdbot / skillhub 都是"装到 --dir 指定的 skills 目录"，共用一套逻辑
  if (s.source === 'clawdbot' || s.source === 'skillhub') {
    const exe = s.source;
    const base = ['install', s.id || s.name];
    let args = s.version ? base.concat(['--version', s.version]) : base.slice();
    args = args.concat(['--dir', targetDir]);
    let r = spawnSync(exe, args, { stdio: 'inherit', shell: IS_WIN });
    if (r.status !== 0 && s.version) {
      // 部分版本 CLI 不支持 --version，去掉重试
      r = spawnSync(exe, base.concat(['--dir', targetDir]), { stdio: 'inherit', shell: IS_WIN });
    }
    if (r.status === 127 || r.status === null && r.error) return `失败：找不到 ${exe} 命令，先装该 CLI`;
    if (r.status !== 0) return `失败：${exe} 调用出错`;
    return null;
  }

  if (s.source === 'git') {
    if (!s.url) return '失败：清单里缺 url';
    const dest = path.join(targetDir, s.name);
    const r = spawnSync('git', ['clone', '--depth', '1', s.url, dest], { stdio: 'inherit' });
    if (r.error) return `失败：无法运行 git：${r.error.message}`;
    if (r.status !== 0) return '失败：git clone 出错';
    if (s.version) spawnSync('git', ['-C', dest, 'checkout', s.version], { stdio: 'inherit' });
    const nested = path.join(dest, 'skills');
    const ok = hasSkillMd(dest) || (fs.existsSync(nested) && subdirsWithSkill(nested).length > 0);
    return ok ? null : '完成但没找到 SKILL.md，检查仓库结构';
  }

  return `暂不支持的来源：${s.source}`;
}

function cmdExt(source, sub, name, opts) {
  const manifest = loadManifest(source);
  const target = extDir(source);

  if (!sub || sub === 'list') {
    console.log(`社区 skills 清单：${path.join(source, EXT_MANIFEST)}`);
    console.log(`安装位置：${target}（不进 git）\n`);
    if (manifest.skills.length === 0) {
      console.log('（空）添加示例：');
      console.log('  skill-sync ext add feishu-docs --source skillhub --version 1.1.1');
      return;
    }
    console.log(`${pad('名称', 20)}${pad('来源', 12)}${pad('版本', 10)}状态`);
    console.log('-'.repeat(58));
    for (const s of manifest.skills) {
      const ok = hasSkillMd(path.join(target, s.name));
      console.log(`${pad(s.name, 20)}${pad(s.source, 12)}${pad(s.version || '-', 10)}${ok ? '已安装' : '未安装'}`);
    }
    return;
  }

  if (sub === 'add') {
    if (!name) { console.error('用法：skill-sync ext add <name> --source clawdbot|skillhub|git [--id <id>] [--url <url>] [--version <v>] [--note <说明>]'); process.exit(1); }
    if (manifest.skills.some((s) => s.name === name)) { console.log(`清单里已有 ${name}`); return; }
    manifest.skills.push({
      name,
      source: opts.source || 'skillhub',
      id: opts.id || name,
      url: opts.url || '',
      version: opts.version || '',
      note: opts.note || '',
    });
    saveManifest(source, manifest);
    console.log(`已加入清单：${name}（来源 ${opts.source || 'skillhub'}）`);
    console.log('执行 skill-sync ext install 安装');
    return;
  }

  if (sub === 'install') {
    fs.mkdirSync(target, { recursive: true });
    const wanted = name ? manifest.skills.filter((s) => s.name === name) : manifest.skills;
    if (wanted.length === 0) { console.log(name ? `清单里没有 ${name}` : '清单为空，先 ext add'); return; }
    for (const s of wanted) {
      const dest = path.join(target, s.name);
      if (hasSkillMd(dest) && !opts.force) { console.log(`  ${pad(s.name, 20)}已安装，跳过（--force 重装）`); continue; }
      if (fs.existsSync(dest)) fs.rmSync(dest, { recursive: true, force: true });
      const err = installOne(s, target);
      console.log(`  ${pad(s.name, 20)}${err || '完成'}`);
    }
    console.log('\n装完执行 skill-sync link 链接到各 AI 工具');
    return;
  }

  console.error(`未知子命令：${sub}（可选：list / add / install）`);
  process.exit(1);
}

function parseOpts(list) {
  const opts = {};
  for (let i = 0; i < list.length; i++) {
    const a = list[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const next = list[i + 1];
      if (next !== undefined && !next.startsWith('--')) { opts[k] = next; i++; } else { opts[k] = true; }
    }
  }
  return opts;
}

// ── 入口 ────────────────────────────────────

const HELP = `
skill-sync —— 一份 Skill 源仓库，分发到本机所有 AI 工具

  skill-sync status                 查看各工具目录的链接状态
  skill-sync link [--force]         为已安装的 AI 工具建立目录链接
  skill-sync unlink <tool>          解除某个工具的链接（只删链接，不动源）
  skill-sync install <name>         用 skillhub 装技能，自动补 --dir
  skill-sync pull                   拉取远端最新
  skill-sync push ["提交信息"]       提交并推送

社区 / 第三方 skills（源码不进 git，只登记来源）
  skill-sync ext list                                查看清单与安装状态
  skill-sync ext add <名字> --source clawdbot --id <作者/名字> [--version v]
  skill-sync ext add <名字> --source skillhub [--version v] [--note 说明]
  skill-sync ext add <名字> --source git --url <仓库> [--version v]
  skill-sync ext install [名字]      按清单安装（省略名字则全部）

选项
  --dir <path>      指定 Skill 源仓库（默认 ~/.workbuddy/skills）
  -h, --help        显示帮助
  -v, --version     显示版本

源仓库解析优先级：--dir > 环境变量 SKILLS_HUB > ~/.skill-sync.json > ~/.workbuddy/skills
`.trim();

function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 0 || argv.includes('-h') || argv.includes('--help')) {
    console.log(HELP); return;
  }
  if (argv.includes('-v') || argv.includes('--version')) {
    console.log(require('../package.json').version); return;
  }

  const dirIdx = argv.indexOf('--dir');
  const dirArg = dirIdx !== -1 ? argv[dirIdx + 1] : null;
  const rest = dirIdx !== -1 ? argv.filter((_, i) => i !== dirIdx && i !== dirIdx + 1) : argv;
  const force = rest.includes('--force');

  const cmd = rest[0];
  const arg1 = rest[1];
  const source = resolveSource(dirArg);

  switch (cmd) {
    case 'status': cmdStatus(source); break;
    case 'link': cmdLink(source, force); break;
    case 'unlink': cmdUnlink(source, arg1); break;
    case 'install': if (!arg1) { console.error('用法：skill-sync install <技能名>'); process.exit(1); } cmdInstall(source, arg1); break;
    case 'pull': cmdPull(source); break;
    case 'push': cmdPush(source, rest.slice(1).join(' ') || null); break;
    case 'ext': cmdExt(source, rest[1], rest[2], Object.assign(parseOpts(rest.slice(1)), { force })); break;
    default: console.error(`未知命令：${cmd}\n`); console.log(HELP); process.exit(1);
  }
}

main();
