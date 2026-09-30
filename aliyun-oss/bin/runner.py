#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aliyun-oss CLI runner —— 载入 aliyun_oss 包并分派子命令。

由 bin/cli.js 调用：
    python runner.py <子命令> [参数...]

输出：stdout 输出结果（默认透传 ossutil 输出，--json 时为 JSON 信封）；
      错误信息写 stderr，并以非 0 退出。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aliyun_oss.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())