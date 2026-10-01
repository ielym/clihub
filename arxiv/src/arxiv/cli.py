"""arxiv CLI：抓取 arXiv Atom 接口并解析为结构化记录。

    arxiv [--query S] [--start N] [--max-results N] [--sort-by F] [--sort-order O]

结果以 JSON 信封输出到 stdout（已解析字段，不含原始 XML）；失败原因写入 stderr 并返回非 0。
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

from . import __version__
from .net import http_get

SOURCE = "arxiv"
API = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv",
        description="抓取 arXiv 论文并输出解析后的结构化 JSON。",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("--query", default="cat:cs.AI", help="检索式，如 cat:cs.AI、au:del_maestro、ti:transformer")
    parser.add_argument("--start", type=int, default=0, help="起始偏移")
    parser.add_argument("--max-results", dest="max_results", type=int, default=20, help="返回条数上限")
    parser.add_argument(
        "--sort-by", dest="sort_by", default="submittedDate",
        choices=["relevance", "lastUpdatedDate", "submittedDate"], help="排序字段",
    )
    parser.add_argument(
        "--sort-order", dest="sort_order", default="descending",
        choices=["ascending", "descending"], help="排序方向",
    )
    return parser


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return " ".join(text.split()) or None


def _atom(node: ET.Element, tag: str) -> Optional[str]:
    el = node.find(f"atom:{tag}", NS)
    return el.text if el is not None else None


def _arxiv(node: ET.Element, tag: str) -> Optional[str]:
    el = node.find(f"arxiv:{tag}", NS)
    return el.text if el is not None else None


def parse_feed(xml_bytes: bytes) -> list:
    root = ET.fromstring(xml_bytes)
    records = []
    for entry in root.findall("atom:entry", NS):
        raw_id = _clean(_atom(entry, "id")) or ""
        source_id = raw_id.rsplit("/abs/", 1)[-1] if "/abs/" in raw_id else raw_id.rsplit("/", 1)[-1]

        authors = []
        for a in entry.findall("atom:author", NS):
            name = _clean(a.findtext("atom:name", default="", namespaces=NS))
            if name:
                authors.append(name)

        categories, primary = [], None
        for c in entry.findall("atom:category", NS):
            term = c.get("term")
            if term:
                categories.append(term)
        pc = entry.find(f"arxiv:primary_category", NS)
        if pc is not None:
            primary = pc.get("term")

        abs_url = pdf_url = None
        for link in entry.findall("atom:link", NS):
            href = link.get("href")
            if not href:
                continue
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = pdf_url or href
            elif link.get("rel") == "alternate":
                abs_url = abs_url or href

        records.append(
            {
                "source": SOURCE,
                "source_id": source_id,
                "title": _clean(_atom(entry, "title")),
                "abstract": _clean(_atom(entry, "summary")),
                "authors": authors,
                "categories": categories,
                "primary_category": primary,
                "published_at": _clean(_atom(entry, "published")),
                "updated_at": _clean(_atom(entry, "updated")),
                "abs_url": abs_url,
                "pdf_url": pdf_url,
                "comment": _clean(_arxiv(entry, "comment")),
                "doi": _clean(_arxiv(entry, "doi")),
                "journal_ref": _clean(_arxiv(entry, "journal_ref")),
            }
        )
    return records


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)
    params = {
        "search_query": args.query,
        "start": args.start,
        "max_results": args.max_results,
        "sortBy": args.sort_by,
        "sortOrder": args.sort_order,
    }

    try:
        xml_bytes = http_get(API, params=params)
    except Exception as e:
        print(f"错误：arxiv 抓取失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    try:
        records = parse_feed(xml_bytes)
    except ET.ParseError as e:
        print(f"错误：arxiv 响应不是合法 Atom XML：{e}", file=sys.stderr)
        return 1

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