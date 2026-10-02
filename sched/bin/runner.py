#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sched CLI runner —— 载入 sched 包并分派子命令。

由 bin/cli.js 调用：
    python3 runner.py <command> [--key value ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sched.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())