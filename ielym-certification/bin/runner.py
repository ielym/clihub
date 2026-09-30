#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ielym-certification CLI runner —— 载入 ielym_certification 包并分派 provider。

由 bin/cli.js 调用：
    python runner.py <provider> [参数...]

输出：stdout 输出凭证内容（--json 时为 JSON 信封）；
      错误信息写 stderr，并以非 0 退出。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ielym_certification.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())