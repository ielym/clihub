"""artificial-analysis CLI：按模态抓取模型评测并解析为结构化记录。

    artificial-analysis [--modality M] [--limit N]

结果以 JSON 信封输出到 stdout（已解析字段）；失败原因写入 stderr 并返回非 0。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .certification import CredentialError, CredentialNotFound, get_credential
from .net import http_get

SOURCE = "artificial-analysis"
ENDPOINTS = {
    "llm": "https://artificialanalysis.ai/api/v2/data/llms/models",
    "text-to-image": "https://artificialanalysis.ai/api/v2/data/media/text-to-image",
    "image-editing": "https://artificialanalysis.ai/api/v2/data/media/image-editing",
    "text-to-speech": "https://artificialanalysis.ai/api/v2/data/media/text-to-speech",
    "text-to-video": "https://artificialanalysis.ai/api/v2/data/media/text-to-video",
    "image-to-video": "https://artificialanalysis.ai/api/v2/data/media/image-to-video",
}

# 已提升为顶层字段的键，其余键整体归入 metrics
_PROMOTED = {"id", "slug", "name", "model_creator", "elo", "rank", "price", "price_per_1m_tokens", "release_date"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="artificial-analysis",
        description="抓取 ArtificialAnalysis 模型评测并输出解析后的结构化 JSON（API Key 来自 OSS 凭证库）。",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument(
        "--modality",
        choices=["all", *ENDPOINTS],
        default="llm",
        help="模态；all 表示遍历全部模态",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多输出条数")
    return parser


def parse_model(model: dict, modality: str) -> dict:
    creator = model.get("model_creator")
    if isinstance(creator, dict):
        creator = creator.get("name") or creator.get("slug")
    return {
        "source": SOURCE,
        "source_id": str(model.get("id") or model.get("slug") or model.get("name")),
        "name": model.get("name"),
        "creator": creator,
        "modality": modality,
        "elo": model.get("elo"),
        "rank": model.get("rank"),
        "price": model.get("price") or model.get("price_per_1m_tokens"),
        "release_date": model.get("release_date"),
        "metrics": {k: v for k, v in model.items() if k not in _PROMOTED},
    }


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)

    try:
        api_key = get_credential()
    except CredentialNotFound:
        print(
            "错误：缺少必需凭据：OSS 凭证库未登记服务 artificial-analysis"
            "（ielym-certification api-key --name artificial-analysis，JSON 字段 AA_API_KEY）",
            file=sys.stderr,
        )
        return 1
    except CredentialError as e:
        print(f"错误：从 OSS 凭证库获取 artificial-analysis 凭据失败：{e}", file=sys.stderr)
        return 1

    headers = {"x-api-key": api_key}
    if args.modality in ENDPOINTS:
        targets = [(args.modality, ENDPOINTS[args.modality])]
    else:
        targets = list(ENDPOINTS.items())

    records = []
    errors = []

    for name, url in targets:
        try:
            data = json.loads(http_get(url, headers=headers))
        except Exception as e:
            errors.append(f"artificial-analysis 模态 {name} 抓取失败：{type(e).__name__}: {e}")
            continue

        models = data.get("data", []) if isinstance(data, dict) else data
        for model in models:
            record = parse_model(model, name)
            if not record["source_id"] or record["source_id"] == "None":
                continue
            records.append(record)
            if args.limit and len(records) >= args.limit:
                break
        if args.limit and len(records) >= args.limit:
            break

    envelope = {
        "source": SOURCE,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": records,
    }
    print(json.dumps(envelope, ensure_ascii=False, indent=2))

    for message in errors:
        print(f"[error] {message}", file=sys.stderr)
    if errors:
        print(f"抓取存在 {len(errors)} 个失败项，详见 stderr", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"抓取失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1