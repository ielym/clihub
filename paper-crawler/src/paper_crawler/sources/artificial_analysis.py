"""ArtificialAnalysis 数据源。

接口：https://artificialanalysis.ai/api/v2/data/... （需 x-api-key）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord

ENDPOINTS = {
    "llm": "https://artificialanalysis.ai/api/v2/data/llms/models",
    "text-to-image": "https://artificialanalysis.ai/api/v2/data/media/text-to-image",
    "image-editing": "https://artificialanalysis.ai/api/v2/data/media/image-editing",
    "text-to-speech": "https://artificialanalysis.ai/api/v2/data/media/text-to-speech",
    "text-to-video": "https://artificialanalysis.ai/api/v2/data/media/text-to-video",
    "image-to-video": "https://artificialanalysis.ai/api/v2/data/media/image-to-video",
}


class ArtificialAnalysisSource(Source):
    name = "artificial_analysis"
    command = "artificial-analysis"
    summary = "ArtificialAnalysis 模型评测（REST API，需 API Key）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        api_key = ctx.credentials.get("aa_api_key", "")
        headers = {"x-api-key": api_key} if api_key else {}

        modality = ctx.params.get("modality")
        # 未指定或 "all" 时遍历全部模态，否则只取指定模态
        targets = [(modality, ENDPOINTS[modality])] if modality in ENDPOINTS else list(ENDPOINTS.items())

        now = datetime.now(timezone.utc)
        for name, url in targets:
            try:
                resp = await http_get(url, headers=headers, ctx=ctx)
                data = resp.json()
            except Exception as e:
                ctx.record_error(f"artificial-analysis 模态 {name} 抓取失败：{type(e).__name__}: {e}")
                continue

            models = data.get("data", []) if isinstance(data, dict) else data
            for m in models:
                mid = m.get("id") or m.get("slug") or m.get("name")
                if not mid:
                    continue
                yield RawRecord(
                    source=self.name,
                    source_id=str(mid),
                    content_type="json",
                    fetched_at=now,
                    data=m,
                    metadata={"modality": name},
                )