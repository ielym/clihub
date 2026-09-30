"""OpenRouter 数据源。

接口：https://openrouter.ai/api/v1/models （OpenAI 兼容）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class OpenRouterSource(Source):
    name = "openrouter"
    command = "openrouter"
    summary = "OpenRouter 模型目录与定价（REST API）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        api_key = ctx.credentials.get("openrouter_api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        resp = await http_get(
            "https://openrouter.ai/api/v1/models", headers=headers, ctx=ctx
        )
        data = resp.json()
        models = data.get("data", []) if isinstance(data, dict) else data
        now = datetime.now(timezone.utc)

        for m in models:
            mid = m.get("id")
            if not mid:
                continue
            yield RawRecord(
                source=self.name,
                source_id=mid,
                content_type="json",
                fetched_at=now,
                data=m,
            )