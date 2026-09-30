"""CVF Open Access 数据源。

无官方接口，抓取静态 HTML 站点。
会议论文列表：https://openaccess.thecvf.com/{Conference}{Year}?day=all
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class CVFSource(Source):
    name = "cvf"
    command = "cvf"
    summary = "CVF Open Access 会议论文（HTML）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        from bs4 import BeautifulSoup

        conferences = ctx.params.get("conferences") or ["CVPR2024"]
        now = datetime.now(timezone.utc)

        for conf in conferences:
            # CVF 需 ?day=all 才列出全部论文
            try:
                resp = await http_get(f"https://openaccess.thecvf.com/{conf}?day=all", ctx=ctx)
            except Exception as e:
                ctx.record_error(f"cvf {conf} 抓取失败：{type(e).__name__}: {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            for dt in soup.select("dt.ptitle"):
                link = dt.select_one("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not href:
                    continue
                paper_id = href.rsplit("/", 1)[-1].replace(".html", "")

                authors_text = ""
                dd = dt.find_next_sibling("dd")
                if dd:
                    authors_text = dd.get_text(strip=True)

                yield RawRecord(
                    source=self.name,
                    source_id=f"{conf}/{paper_id}",
                    content_type="json",
                    fetched_at=now,
                    data={"title": title, "authors": authors_text, "href": href},
                    metadata={"conference": conf, "href": href},
                )