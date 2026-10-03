#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sched CLI runner —— 定位 scheduler 代码仓并调用 sched 包入口。

由 bin/cli.js 调用：
    python3 runner.py <command> [options]

scheduler 是独立代码仓（github.com/ielym/scheduler），运行时需要其中的 sched/
与 sched_task_sdk/ 两个包。代码根按以下顺序发现，全程无硬编码绝对路径：

    1. 环境变量 SCHED_REPO（显式指定代码仓根）
    2. 环境变量 SCHED_HOME（调度器项目根，与代码仓根同构）
    3. 当前工作目录及其各级父目录（在仓库内任意位置调用均可）
    4. ~/scheduler（约定的 clone 位置）
    5. 已安装到解释器环境的 sched 包（pip install -e <代码仓>）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for var in ("SCHED_REPO", "SCHED_HOME"):
        value = os.environ.get(var)
        if value:
            roots.append(Path(value).expanduser())
    cwd = Path.cwd()
    roots.append(cwd)
    roots.extend(cwd.parents)
    roots.append(Path.home() / "scheduler")
    return roots


def _resolve_repo_root() -> Path | None:
    for root in _candidate_roots():
        if (root / "sched" / "__init__.py").is_file() and (
            root / "sched_task_sdk"
        ).is_dir():
            return root.resolve()
    return None


def _fail_no_repo() -> int:
    sys.stderr.write(
        "错误：找不到 scheduler 代码仓（需要同时包含 sched/ 与 sched_task_sdk/ 包的目录）。\n"
        "请先获取代码：\n"
        "    git clone https://github.com/ielym/scheduler.git\n"
        "然后任选一种方式后重试：\n"
        "    1. 在该仓库目录内执行 sched 命令（自动向上发现代码根）；\n"
        "    2. export SCHED_REPO=/path/to/scheduler；\n"
        "    3. pip install -e /path/to/scheduler（安装为原生 sched 命令）。\n"
    )
    return 2


def main() -> int:
    root = _resolve_repo_root()
    if root is not None and str(root) not in sys.path:
        # 必须插到 0：Python 标准库自带 sched 模块，需要让代码仓包优先。
        sys.path.insert(0, str(root))
    try:
        from sched.__main__ import main as sched_main
    except ImportError:
        return _fail_no_repo()
    return sched_main()


if __name__ == "__main__":
    sys.exit(main())
