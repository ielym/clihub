"""paper-crawler 命令行入口。

每个数据源对应一条独立指令，抓取结果以 JSON 输出到 stdout：
    paper-crawler <数据源指令> [参数...]
    paper-crawler sources
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from . import __version__
from .base import Source
from .context import FetchContext
from .raw import RawRecord
from .registry import all_sources, by_name

# 凭据数据源：CLI 参数名 -> 凭据键 -> 环境变量候选 -> 是否必需
CREDENTIAL_SPEC = {
    "openreview": [("token", "token", ("OPENREVIEW_TOKEN",), True)],
    "huggingface_papers": [("token", "hf_token", ("HF_TOKEN", "HUGGINGFACE_TOKEN"), False)],
    "artificial_analysis": [("api_key", "aa_api_key", ("AA_API_KEY",), True)],
    "openrouter": [("api_key", "openrouter_api_key", ("OPENROUTER_API_KEY",), False)],
}


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _add_credential_args(parser: argparse.ArgumentParser, source_name: str) -> None:
    for arg, _key, _envs, _required in CREDENTIAL_SPEC.get(source_name, []):
        parser.add_argument(
            f"--{arg.replace('_', '-')}",
            dest=arg,
            default=None,
            help="凭据（未传时读取对应环境变量）",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-crawler",
        description="多数据源原始抓取 CLI：每个数据源一条独立指令，输出原始记录 JSON。",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="列出全部数据源指令")
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("arxiv", help="arXiv 预印本（Atom API）")
    p.add_argument("--query", default="cat:*", help="arXiv 检索式；默认 cat:* 覆盖全部分类，如 cat:cs.AI、cat:math.NT、au:del_maestro")
    p.add_argument("--max-results", dest="max_results", type=int, default=50, help="单次请求返回条数")
    p.add_argument("--start", type=int, default=0, help="起始偏移")
    p.add_argument("--sort-by", dest="sort_by", default="submittedDate")
    p.add_argument("--sort-order", dest="sort_order", default="descending")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="arxiv")

    p = sub.add_parser("github-trending", help="GitHub Trending 榜单（HTML）")
    p.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily")
    p.add_argument("--language", default="", help="按语言过滤，如 python")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="github_trending")

    p = sub.add_parser("openreview", help="OpenReview 投稿/评审（需凭据）")
    p.add_argument("--venue-id", dest="venue_id", default="ICLR.cc/2024/Conference")
    p.add_argument("--status", default="accepted")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=None, help="最多输出条数（同时作为接口页大小，默认 100）")
    _add_credential_args(p, "openreview")
    p.set_defaults(func=cmd_fetch, source="openreview")

    p = sub.add_parser("huggingface-papers", help="HuggingFace Daily Papers（REST API）")
    p.add_argument("--date", default=None, help="日期 YYYY-MM-DD")
    p.add_argument("--sort", default=None, help="排序字段")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数（同时作为接口页大小，默认 50）")
    _add_credential_args(p, "huggingface_papers")
    p.set_defaults(func=cmd_fetch, source="huggingface_papers")

    p = sub.add_parser("artificial-analysis", help="ArtificialAnalysis 模型评测（需 API Key）")
    p.add_argument(
        "--modality",
        choices=["all", "llm", "text-to-image", "image-editing", "text-to-speech", "text-to-video", "image-to-video"],
        default="llm",
        help="模态，all 表示遍历全部模态",
    )
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    _add_credential_args(p, "artificial_analysis")
    p.set_defaults(func=cmd_fetch, source="artificial_analysis")

    p = sub.add_parser("openrouter", help="OpenRouter 模型目录与定价（REST API）")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    _add_credential_args(p, "openrouter")
    p.set_defaults(func=cmd_fetch, source="openrouter")

    p = sub.add_parser("acl-anthology", help="ACL Anthology 会议论文（GitHub XML）")
    p.add_argument("--collections", default="2024.acl", help="逗号分隔的 collection id，如 2024.acl,2023.emnlp")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="acl_anthology")

    p = sub.add_parser("pmlr", help="PMLR 论文集（HTML）")
    p.add_argument("--volumes", default="235", help="逗号分隔的卷号，如 235,202")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="pmlr")

    p = sub.add_parser("cvf", help="CVF Open Access 会议论文（HTML）")
    p.add_argument("--conferences", default="CVPR2024", help="逗号分隔的会议标识，如 CVPR2024,ICCV2023")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="cvf")

    p = sub.add_parser("dblp", help="DBLP 文献库（XML dump）")
    p.add_argument("--mode", choices=["sample", "local", "download"], default="sample", help="sample=内置样本，local=本地 dump，download=下载最新 dump")
    p.add_argument("--dump", default=None, help="mode=local 时的本地 XML / XML.GZ 路径")
    p.add_argument("--limit", type=int, default=None, help="最多输出条数")
    p.set_defaults(func=cmd_fetch, source="dblp")

    return parser


def build_params(name: str, args: argparse.Namespace) -> dict:
    if name == "arxiv":
        return {
            "query": args.query,
            "max_results": args.max_results,
            "start": args.start,
            "sort_by": args.sort_by,
            "sort_order": args.sort_order,
        }
    if name == "github_trending":
        return {"since": args.since, "language": args.language}
    if name == "openreview":
        return {
            "venue_id": args.venue_id,
            "status": args.status,
            "offset": args.offset,
            "limit": args.limit or 100,
        }
    if name == "huggingface_papers":
        params: dict = {"limit": args.limit or 50}
        if args.date:
            params["date"] = args.date
        if args.sort:
            params["sort"] = args.sort
        return params
    if name == "artificial_analysis":
        return {"modality": args.modality}
    if name == "acl_anthology":
        return {"collections": _csv(args.collections)}
    if name == "pmlr":
        return {"volumes": [int(v) for v in _csv(args.volumes)]}
    if name == "cvf":
        return {"conferences": _csv(args.conferences)}
    if name == "dblp":
        params = {"mode": args.mode}
        if args.mode == "local" and args.dump:
            params["dump"] = args.dump
        return params
    return {}


def build_credentials(name: str, args: argparse.Namespace) -> dict:
    credentials: dict[str, str] = {}
    for arg, key, envs, _required in CREDENTIAL_SPEC.get(name, []):
        value = getattr(args, arg, None)
        if not value:
            for env in envs:
                if os.environ.get(env):
                    value = os.environ[env]
                    break
        if value:
            credentials[key] = value
    return credentials


async def _collect(source: Source, ctx: FetchContext, limit: int | None) -> list[RawRecord]:
    records: list[RawRecord] = []
    async for raw in source.fetch(ctx):
        records.append(raw)
        if limit and len(records) >= limit:
            break
    return records


def cmd_fetch(args: argparse.Namespace) -> int:
    source = by_name(args.source)
    if source is None:
        print(f"未知数据源: {args.source}", file=sys.stderr)
        return 1

    params = build_params(source.name, args)
    credentials = build_credentials(source.name, args)

    missing = [
        (arg, envs)
        for arg, key, envs, required in CREDENTIAL_SPEC.get(source.name, [])
        if required and key not in credentials
    ]
    if missing:
        for arg, envs in missing:
            print(
                f"错误：缺少必需凭据 --{arg.replace('_', '-')}"
                f"（或环境变量 {' / '.join(envs)}）",
                file=sys.stderr,
            )
        return 1

    ctx = FetchContext(params=params, credentials=credentials, rate_limit=source.rate_limit)
    records = asyncio.run(_collect(source, ctx, args.limit))

    envelope = {
        "source": source.name,
        "command": source.command,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": [r.to_dict() for r in records],
    }
    print(json.dumps(envelope, ensure_ascii=False, indent=2))

    if ctx.errors:
        print(f"抓取存在 {len(ctx.errors)} 个失败项，详见 stderr", file=sys.stderr)
        return 1
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    data = [
        {"command": s.command, "source": s.name, "summary": s.summary}
        for s in all_sources()
    ]
    print(json.dumps({"count": len(data), "sources": data}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"抓取失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1