#!/usr/bin/env node
'use strict';

/**
 * skill-sync —— 一份 Skill 源仓库，分发到本机所有 AI 工具。
 *
 * 用法:
 *   skill-sync init <目录>             记录源仓库位置（~/.skill-sync.json）
 *   skill-sync status                  查看各工具目录的链接状态
 *   skill-sync link [--force]          为已安装的 AI 工具建立目录链接
 *   skill-sync unlink <tool>           解除某个工具的链接
 *   skill-sync update [--force]        拉取自建 + 更新外部 skill + 重新链接（一键同步）
 *   skill-sync pull / push ["msg"]     拉取 / 提交推送（自建 skill）
 *   skill-sync install <name> --url <...>  登记并安装一个外部 skill
 *   skill-sync ext list|add|install    管理外部 skill（git / url 两种来源）
 *
 * 仅用 Node 内置模块；下载解压借用系统自带 curl / tar（或 PowerShell）。
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
  return null;
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

// ── 外部 skill 安装（git / url 两种来源）──

function findSkillRoot(dir) {
  if (hasSkillMd(dir)) return dir;
  const subs = fs.readdirSync(dir).filter((n) => !n.startsWith('.'));
  if (subs.length === 1) {
    const one = path.join(dir, subs[0]);
    try { if (fs.statSync(one).isDirectory() && hasSkillMd(one)) return one; } catch { /* ignore */ }
  }
  return null;
}

function downloadFile(url, dest) {
  const exe = IS_WIN ? 'curl.exe' : 'curl';
  const r = spawnSync(exe, ['-sSL', url, '-o', dest], { stdio: ['ignore', 'inherit', 'inherit'] });
  if (r.error) return `失败：无法下载（需要 curl）——${r.error.message}`;
  if (r.status !== 0) return `失败：下载出错（curl 退出码 ${r.status}）`;
  return null;
}

function extractArchive(archive, dest) {
  fs.mkdirSync(dest, { recursive: true });
  const isZip = /\.zip$/i.test(archive);
  let r;
  if (IS_WIN) {
    if (isZip) {
      const cmd = `Expand-Archive -LiteralPath '${archive.replace(/'/g, "''")}' -DestinationPath '${dest.replace(/'/g, "''")}' -Force`;
      r = spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-Command', cmd], { stdio: ['ignore', 'inherit', 'inherit'] });
    } else {
      r = spawnSync('tar', ['-xf', archive, '-C', dest], { stdio: ['ignore', 'inherit', 'inherit'] });
    }
  } else {
    if (isZip) {
      r = spawnSync('unzip', ['-q', '-o', archive, '-d', dest], { stdio: ['ignore', 'inherit', 'inherit'] });
    } else {
      r = spawnSync('tar', ['-xf', archive, '-C', dest], { stdio: ['ignore', 'inherit', 'inherit'] });
    }
  }
  if (r.error) return `失败：无法解压——${r.error.message}`;
  if (r.status !== 0) return '失败：解压出错';
  return null;
}

function keepSecrets(dir) {
  // url 源更新是「整体替换」，需保留旧目录里的 .env 密钥等本地文件
  const kept = {};
  try {
    for (const f of fs.readdirSync(dir)) {
      if (f === '.env' || f.startsWith('.env.')) {
        kept[f] = fs.readFileSync(path.join(dir, f));
      }
    }
  } catch { /* ignore */ }
  return kept;
}

function restoreSecrets(dir, kept) {
  for (const [f, buf] of Object.entries(kept)) {
    try { fs.writeFileSync(path.join(dir, f), buf); } catch { /* ignore */ }
  }
}

/**
 * 安装 / 更新一个外部 skill 到 targetDir/<name>。
 * 返回错误信息字符串，成功返回 null。
 */
function installOne(s, targetDir) {
  const dest = path.join(targetDir, s.name);

  if (s.source === 'git') {
    if (!s.url) return '失败：清单里缺 url';
    if (fs.existsSync(path.join(dest, '.git'))) {
      const pr = spawnSync('git', ['-C', dest, 'pull', '--rebase', '--autostash'], { stdio: ['ignore', 'inherit', 'inherit'] });
      if (pr.error) return `失败：无法运行 git：${pr.error.message}`;
      if (pr.status !== 0) return '失败：git pull 出错';
    } else {
      if (fs.existsSync(dest)) fs.rmSync(dest, { recursive: true, force: true });
      const r = spawnSync('git', ['clone', '--depth', '1', s.url, dest], { stdio: ['ignore', 'inherit', 'inherit'] });
      if (r.error) return `失败：无法运行 git：${r.error.message}`;
      if (r.status !== 0) return '失败：git clone 出错';
    }
    if (s.version) {
      const v = spawnSync('git', ['-C', dest, 'checkout', s.version], { stdio: ['ignore', 'inherit', 'inherit'] });
      if (v.status !== 0) return '失败：checkout 版本出错';
    }
    const nested = path.join(dest, 'skills');
    const ok = hasSkillMd(dest) || (fs.existsSync(nested) && subdirsWithSkill(nested).length > 0);
    return ok ? null : '完成但没找到 SKILL.md，检查仓库结构';
  }

  if (s.source === 'url') {
    if (!s.url) return '失败：清单里缺 url';
    const kept = fs.existsSync(dest) ? keepSecrets(dest) : {};
    const tmp = path.join(os.tmpdir(), `skill-sync-${s.name}`);
    fs.rmSync(tmp, { recursive: true, force: true });
    fs.mkdirSync(tmp, { recursive: true });

    const urlPath = s.url.split('?')[0];
    const m = urlPath.match(/\.(zip|tar|tar\.gz|tgz)$/i);
    const ext = m ? m[1] : 'zip';
    const archive = path.join(tmp, `pkg.${ext}`);

    let e = downloadFile(s.url, archive);
    if (e) { fs.rmSync(tmp, { recursive: true, force: true }); return e; }

    const stage = path.join(tmp, 'stage');
    e = extractArchive(archive, stage);
    if (e) { fs.rmSync(tmp, { recursive: true, force: true }); return e; }

    const root = findSkillRoot(stage);
    if (!root) { fs.rmSync(tmp, { recursive: true, force: true }); return '完成但没找到 SKILL.md，检查包结构'; }

    if (fs.existsSync(dest)) fs.rmSync(dest, { recursive: true, force: true });
    fs.cpSync(root, dest, { recursive: true });
    restoreSecrets(dest, kept);
    fs.rmSync(tmp, { recursive: true, force: true });
    return null;
  }

  return `暂不支持的来源：${s.source}（只支持 git / url）`;
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
    console.error(`源仓库不存在：${source}`);
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

function cmdInit(p) {
  if (!p) { console.error('用法：skill-sync init <源仓库路径>'); process.exit(1); }
  const abs = path.resolve(p);
  if (!fs.existsSync(abs)) { console.error(`路径不存在：${abs}`); process.exit(1); }
  saveSource(abs);
  console.log(`已设置 Skill 源仓库：${abs}`);
  console.log(`（写入 ${CONFIG_PATH}）`);
  console.log('下一步：skill-sync link');
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

function extInstall(source, name, opts) {
  const manifest = loadManifest(source);
  const target = extDir(source);
  fs.mkdirSync(target, { recursive: true });
  const wanted = name ? manifest.skills.filter((s) => s.name === name) : manifest.skills;
  if (wanted.length === 0) { console.log(name ? `清单里没有 ${name}` : '清单为空，先 ext add'); return; }

  for (const s of wanted) {
    const dest = path.join(target, s.name);
    const existed = fs.existsSync(dest);
    if (existed && opts.force) fs.rmSync(dest, { recursive: true, force: true });
    const err = installOne(s, target);
    console.log(`  ${pad(s.name, 20)}${err || (existed && !opts.force ? '已更新' : '完成')}`);
  }
}

function cmdInstall(source, name, opts) {
  if (!name) {
    console.error('用法：skill-sync install <名字> --source git|url --url <地址> [--version v]');
    process.exit(1);
  }
  const m = loadManifest(source);
  let s = m.skills.find((x) => x.name === name);
  if (!s) {
    const src = opts.source || 'git';
    if (!opts.url) { console.error('首次安装需指定 --url <仓库/下载地址>'); process.exit(1); }
    s = { name, source: src, id: name, url: opts.url, version: opts.version || '', note: opts.note || '' };
    m.skills.push(s);
    saveManifest(source, m);
    console.log(`已登记：${name}（来源 ${src}）`);
  }

  const target = extDir(source);
  fs.mkdirSync(target, { recursive: true });
  const dest = path.join(target, name);
  const existed = fs.existsSync(dest);
  if (existed && opts.force) fs.rmSync(dest, { recursive: true, force: true });
  const err = installOne(s, target);
  console.log(`  ${pad(name, 20)}${err || (existed && !opts.force ? '已更新' : '完成')}`);

  console.log('\n自动执行 link ...');
  cmdLink(source, opts.force);
}

function cmdUpdate(source, opts) {
  console.log('① 拉取自建 skill（git pull）...');
  if (git(source, ['pull', '--rebase', '--autostash']) !== 0) {
    console.error('\ngit pull 失败，请先处理后再试');
    process.exit(1);
  }
  console.log('\n② 更新外部 skills ...');
  extInstall(source, null, opts);
  console.log('\n③ 重新链接到各 AI 工具 ...');
  cmdLink(source, opts.force);
}

function cmdExt(source, sub, name, opts) {
  const manifest = loadManifest(source);
  const target = extDir(source);

  if (!sub || sub === 'list') {
    console.log(`社区 skills 清单：${path.join(source, EXT_MANIFEST)}`);
    console.log(`安装位置：${target}（不进 git）\n`);
    if (manifest.skills.length === 0) {
      console.log('（空）添加示例：');
      console.log('  skill-sync ext add feishu-docs --source url --url <下载地址>');
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
    if (!name) {
      console.error('用法：skill-sync ext add <名字> --source git|url --url <地址> [--version v] [--note 说明]');
      process.exit(1);
    }
    if (manifest.skills.some((s) => s.name === name)) { console.log(`清单里已有 ${name}`); return; }
    const src = opts.source || 'git';
    if (!opts.url) { console.error('需指定 --url <仓库/下载地址>'); process.exit(1); }
    manifest.skills.push({
      name,
      source: src,
      id: name,
      url: opts.url,
      version: opts.version || '',
      note: opts.note || '',
    });
    saveManifest(source, manifest);
    console.log(`已加入清单：${name}（来源 ${src}）`);
    console.log('执行 skill-sync ext install 安装');
    return;
  }

  if (sub === 'install') {
    extInstall(source, name, opts);
    console.log('\n自动执行 link ...');
    cmdLink(source, opts.force);
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

  skill-sync init <目录>            记录源仓库位置（~/.skill-sync.json）
  skill-sync status                 查看各工具目录的链接状态
  skill-sync link [--force]         为已安装的 AI 工具建立目录链接
  skill-sync unlink <tool>          解除某个工具的链接（只删链接，不动源）
  skill-sync update [--force]       一键同步：拉取自建 + 更新外部 + 重新链接
  skill-sync pull                   仅拉取自建 skill（git pull）
  skill-sync push ["提交信息"]      提交并推送自建 skill
  skill-sync install <名字> --source git|url --url <地址>   登记并安装一个外部 skill

社区 / 第三方 skills（源码不进 git，只登记来源）
  skill-sync ext list                               查看清单与安装状态
  skill-sync ext add <名字> --source git|url --url <地址> [--version v]
  skill-sync ext install [名字]                     安装 / 更新（已装则更新），装完自动 link

选项
  --dir <path>     指定 Skill 源仓库（否则用 init 记录的路径）
  --force          link 遇非空目录先备份重链 / 安装强制重装
  -h, --help       显示帮助
  -v, --version    显示版本

源仓库解析优先级：--dir > 环境变量 SKILLS_HUB > ~/.skill-sync.json（init 写入）
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

  if (cmd === 'init') { cmdInit(arg1 || dirArg); return; }

  const source = resolveSource(dirArg);
  if (!source) {
    console.error('未找到 Skill 源仓库。请先指定：');
    console.error('  skill-sync init <源仓库路径>');
    console.error('  或每次带 --dir <路径>');
    process.exit(1);
  }

  switch (cmd) {
    case 'status': cmdStatus(source); break;
    case 'link': cmdLink(source, force); break;
    case 'unlink': cmdUnlink(source, arg1); break;
    case 'install': cmdInstall(source, arg1, Object.assign(parseOpts(rest.slice(1)), { force })); break;
    case 'update': cmdUpdate(source, { force }); break;
    case 'pull': cmdPull(source); break;
    case 'push': cmdPush(source, rest.slice(1).join(' ') || null); break;
    case 'ext': cmdExt(source, rest[1], rest[2], Object.assign(parseOpts(rest.slice(1)), { force })); break;
    default: console.error(`未知命令：${cmd}\n`); console.log(HELP); process.exit(1);
  }
}

main();