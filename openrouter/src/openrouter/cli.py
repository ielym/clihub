"""openrouter CLI：抓取模型目录并解析为结构化记录。

    openrouter [--limit N]

结果以 JSON 信封输出到 stdout（已解析字段）；失败原因写入 stderr 并返回非 0。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .certification import CredentialError, get_optional_credential
from .net import http_get

SOURCE = "openrouter"
API = "https://openrouter.ai/api/v1/models"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openrouter",
        description="抓取 OpenRouter 模型目录并输出解析后的结构化 JSON。",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("--limit", type=int, default=None, help="最多输出条数")
    return parser


def _parse_model(model: dict) -> dict:
    arch = model.get("architecture") or {}
    created = model.get("created")
    created_at = (
        datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
        if isinstance(created, (int, float)) else None
    )
    provider = model.get("top_provider") or {}
    return {
        "source": SOURCE,
        "source_id": model.get("id"),
        "name": model.get("name"),
        "description": model.get("description"),
        "context_length": model.get("context_length"),
        "created_at": created_at,
        "modality": arch.get("modality"),
        "input_modalities": arch.get("input_modalities"),
        "output_modalities": arch.get("output_modalities"),
        "pricing": model.get("pricing"),
        "top_provider": {
            "context_length": provider.get("context_length"),
            "max_completion_tokens": provider.get("max_completion_tokens"),
            "is_moderated": provider.get("is_moderated"),
        } if provider else None,
        "supported_parameters": model.get("supported_parameters"),
    }


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)

    try:
        api_key = get_optional_credential()
    except CredentialError as e:
        print(f"错误：从 OSS 凭证库获取 openrouter 凭据失败：{e}", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        payload = json.loads(http_get(API, headers=headers))
    except Exception as e:
        print(f"错误：openrouter 模型目录抓取失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    records = [_parse_model(m) for m in payload.get("data", []) if m.get("id")]
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