"""HuggingFace Daily Papers 数据源。

接口：
  - GET /api/daily_papers          每日热门论文列表
  - GET /api/papers/{arxiv_id}     单篇结构化元数据
无认证即可访问，携带 HF token 配额更高。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class HuggingFacePapersSource(Source):
    name = "huggingface_papers"
    command = "huggingface-papers"
    summary = "HuggingFace Daily Papers（REST API）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        base = "https://huggingface.co"
        token = ctx.credentials.get("hf_token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        params = {"limit": int(ctx.params.get("limit", 50))}
        if ctx.params.get("date"):
            params["date"] = ctx.params["date"]
        if ctx.params.get("sort"):
            params["sort"] = ctx.params["sort"]

        resp = await http_get(
            f"{base}/api/daily_papers", params=params, headers=headers, ctx=ctx
        )
        daily = resp.json()
        now = datetime.now(timezone.utc)

        for item in daily:
            paper_id = item.get("paper", {}).get("id") or item.get("id")
            if not paper_id:
                continue
            try:
                detail_resp = await http_get(
                    f"{base}/api/papers/{paper_id}", headers=headers, ctx=ctx
                )
                detail = detail_resp.json()
            except Exception as e:
                ctx.warn(f"huggingface 论文 {paper_id} 详情抓取失败，回退列表数据：{type(e).__name__}: {e}")
                detail = item.get("paper", item)

            yield RawRecord(
                source=self.name,
                source_id=paper_id,
                content_type="json",
                fetched_at=now,
                data={"daily": item, "detail": detail},
                metadata={"upvotes": item.get("paper", {}).get("upvotes", 0)},
            )