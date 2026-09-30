"""PMLR 数据源（Proceedings of Machine Learning Research）。

无官方接口，抓取静态 HTML 站点。
论文集 URL：https://proceedings.mlr.press/v{volume}/
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class PMLRSource(Source):
    name = "pmlr"
    command = "pmlr"
    summary = "PMLR 论文集（HTML）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        from bs4 import BeautifulSoup

        volumes = ctx.params.get("volumes") or [235]
        now = datetime.now(timezone.utc)

        for vol in volumes:
            try:
                resp = await http_get(f"https://proceedings.mlr.press/v{vol}/", ctx=ctx)
            except Exception as e:
                ctx.record_error(f"pmlr v{vol} 抓取失败：{type(e).__name__}: {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            booktitle = ""
            h2 = soup.select_one("h2")
            if h2:
                booktitle = h2.get_text(strip=True)

            entries = soup.select("div.paper, div.entry")
            if not entries:
                entries = soup.select("p.links")

            for entry in entries:
                link = entry.select_one("a[href$='.html']")
                if not link:
                    continue
                href = link.get("href", "")
                paper_id = href.rsplit("/", 1)[-1].replace(".html", "")
                if not paper_id:
                    continue
                yield RawRecord(
                    source=self.name,
                    source_id=f"v{vol}/{paper_id}",
                    content_type="html",
                    fetched_at=now,
                    data=str(entry),
                    metadata={"volume": vol, "booktitle": booktitle, "href": href},
                )