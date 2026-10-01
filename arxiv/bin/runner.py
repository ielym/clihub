#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arxiv CLI runner —— 载入 arxiv 包并分派抓取。

由 bin/cli.js 调用：
    python runner.py [--query S] [--start N] [--max-results N] [--sort-by F] [--sort-order O]

输出：stdout 输出结构化 JSON（成功）或错误信息（stderr，exit 1）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from arxiv.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())