#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""artificial-analysis CLI runner —— 载入 artificial_analysis 包并分派抓取。

由 bin/cli.js 调用：
    python runner.py [--modality M] [--limit N]

输出：stdout 输出 JSON（成功）或错误信息（stderr，exit 1）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from artificial_analysis.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())