# skill-sync

一份 Skill 源仓库，链接到本机所有 AI 工具。物理上只存一份，各工具的 skills 目录用目录链接指向它，不产生副本——改一处，处处生效。

Windows 用 junction（`mklink /J`，无需管理员），macOS/Linux 用 symlink。零依赖，只用 Node 内置模块。

## 安装

```bash
npm i -g @ielym/skill-sync   # 全局安装，得到 skill-sync 命令
npx @ielym/skill-sync status # 或临时跑一次，不落盘
```

## 使用

```bash
skill-sync status          # 查看各 AI 工具的链接状态
skill-sync link            # 为已安装的工具建立链接
skill-sync link --force    # 目标目录非空时先备份再链接
skill-sync unlink claude   # 解除某个工具的链接（只删链接，不动源文件）
skill-sync pull            # 拉取远端最新
skill-sync push "更新说明"  # 提交并推送
```

### 源仓库位置

按以下优先级解析，一般不用管：

1. `--dir <path>` 显式指定
2. 环境变量 `SKILLS_HUB`
3. `~/.skill-sync.json` 里的 `hub` 字段（`link` 时自动写入）
4. 默认 `~/.workbuddy/skills`

## 支持的 AI 工具

| 工具 | skills 目录 |
|---|---|
| WorkBuddy | `~/.workbuddy/skills` |
| Claude Code | `~/.claude/skills` |
| Cursor | `~/.cursor/skills` |
| Windsurf | `~/.codeium/windsurf/skills` |
| Codex | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |
| Antigravity | `~/.gemini/antigravity/skills` |
| QoderWork | `~/.qoderwork/skills` |

父目录存在才认为该工具已安装，不会给没装的工具建空目录。

## 注意

- `link` 遇到非空目标目录默认跳过，`--force` 会把原目录备份成 `skills.bak-<时间戳>`。
- `unlink` 只删链接本身，源仓库文件不受影响。
- 带 `node_modules` 的技能建议只提交源码，新机器进入目录自行 `npm install`。

## License

MIT
