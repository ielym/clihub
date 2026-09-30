"""arXiv 数据源。

接口：http://export.arxiv.org/api/query （Atom 1.0 XML）
默认检索式 cat:* 覆盖全部学科分类，可按需指定任意 arXiv 检索式。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord

ATOM_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivSource(Source):
    name = "arxiv"
    command = "arxiv"
    summary = "arXiv 预印本（Atom API）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=3.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        from lxml import etree

        query = ctx.params.get("query") or "cat:*"
        payload = {
            "search_query": query,
            "start": int(ctx.params.get("start", 0)),
            "max_results": int(ctx.params.get("max_results", 50)),
            "sortBy": ctx.params.get("sort_by", "submittedDate"),
            "sortOrder": ctx.params.get("sort_order", "descending"),
        }
        resp = await http_get("https://export.arxiv.org/api/query", params=payload, ctx=ctx)
        root = etree.fromstring(resp.content)
        now = datetime.now(timezone.utc)

        for entry in root.findall("a:entry", ATOM_NS):
            id_url = entry.findtext("a:id", "", namespaces=ATOM_NS)
            arxiv_id = id_url.rsplit("/", 1)[-1]
            yield RawRecord(
                source=self.name,
                source_id=arxiv_id,
                content_type="atom_xml",
                fetched_at=now,
                data=etree.tostring(entry, encoding="unicode"),
                metadata={"query": query},
            )