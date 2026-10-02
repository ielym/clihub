"""ip-tunnel CLI runner —— 载入 ip_tunnel 包并分派。

由 bin/cli.js 调用：
    python runner.py <command> [options]

stdout 输出结果（默认人类可读或 JSON 信封）；错误信息写 stderr 并返回非 0。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ip_tunnel.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())