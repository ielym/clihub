"""github-trending CLI：抓取 Trending 页面并解析为结构化记录。

    github-trending [--since daily|weekly|monthly] [--language LANG]

结果以 JSON 信封输出到 stdout（已解析字段，不含原始 HTML）；失败原因写入 stderr 并返回非 0。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional

from . import __version__
from .net import http_get

SOURCE = "github-trending"
BASE = "https://github.com/trending"


class _TrendingParser(HTMLParser):
    """从 Trending 页面解析出仓库条目。

    依赖页面结构：每个仓库为 `<article class="Box-row">`，其中
    仓库链接位于 `h2 > a[href="/owner/repo"]`，描述为 `p.color-fg-muted`，
    语言为 `span[itemprop=programmingLanguage]`，star / fork 为
    `a[href$=/stargazers|/forks]`，当日新增 star 为 `span.float-sm-right`。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list = []
        self._depth = 0
        self._cur: Optional[dict] = None
        self._h2_depth: Optional[int] = None
        self._cap: Optional[str] = None
        self._cap_depth: Optional[int] = None
        self._buf: list = []

    def _begin(self, field: str) -> None:
        if self._cap is None:
            self._cap = field
            self._cap_depth = self._depth
            self._buf = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        cls = attr.get("class") or ""
        self._depth += 1

        if tag == "article" and "Box-row" in cls:
            self._cur = {
                "source_id": None, "url": None, "description": None,
                "language": None, "stars": None, "forks": None, "stars_today": None,
            }
            return
        if self._cur is None:
            return

        if tag == "h2" and self._h2_depth is None:
            self._h2_depth = self._depth
        elif tag == "a" and self._h2_depth is not None and not self._cur["source_id"]:
            href = (attr.get("href") or "").strip()
            if href.startswith("/") and href.count("/") == 2 and "?" not in href and "#" not in href:
                repo = href.strip("/")
                self._cur["source_id"] = repo
                self._cur["url"] = f"https://github.com/{repo}"
        elif tag == "p" and "color-fg-muted" in cls and self._cur["description"] is None:
            self._begin("description")
        elif tag == "span" and attr.get("itemprop") == "programmingLanguage":
            self._begin("language")
        elif tag == "span" and "float-sm-right" in cls:
            self._begin("stars_today")
        elif tag == "a":
            href = attr.get("href") or ""
            if href.endswith("/stargazers"):
                self._begin("stars")
            elif href.endswith("/forks"):
                self._begin("forks")

    def handle_data(self, data):
        if self._cap is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._cur is not None:
            if tag == "h2" and self._h2_depth == self._depth:
                self._h2_depth = None
            if self._cap is not None and self._depth == self._cap_depth:
                text = " ".join("".join(self._buf).split())
                self._cur[self._cap] = text or None
                self._cap = None
                self._buf = []
            if tag == "article":
                self._finish()
        self._depth -= 1

    def _finish(self) -> None:
        cur, self._cur = self._cur, None
        if cur and cur.get("source_id"):
            self.records.append(cur)


def _to_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    s = text.lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([km])?\b", s)
    if not match:
        return None
    value = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        value *= 1000
    elif suffix == "m":
        value *= 1_000_000
    return int(value)


def parse_html(html_bytes: bytes) -> list:
    parser = _TrendingParser()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    parser.close()
    records = []
    for rank, item in enumerate(parser.records, start=1):
        records.append(
            {
                "source": SOURCE,
                "rank": rank,
                "source_id": item["source_id"],
                "url": item["url"],
                "description": item["description"],
                "language": item["language"],
                "stars": _to_int(item["stars"]),
                "forks": _to_int(item["forks"]),
                "stars_today": _to_int(item["stars_today"]),
            }
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-trending",
        description="抓取 GitHub Trending 榜单并输出解析后的结构化 JSON。",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"], help="榜单周期")
    parser.add_argument("--language", default=None, help="语言作为路径段，如 python、rust")
    parser.add_argument("--limit", type=int, default=None, help="最多输出条数")
    return parser


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)
    url = f"{BASE}/{args.language}" if args.language else BASE

    try:
        html_bytes = http_get(url, params={"since": args.since})
    except Exception as e:
        print(f"错误：github-trending 抓取失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    records = parse_html(html_bytes)
    if args.limit is not None:
        records = records[: args.limit]

    envelope = {
        "source": SOURCE,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": records,
    }
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"抓取失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1