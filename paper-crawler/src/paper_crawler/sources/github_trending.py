"""GitHub Trending 数据源。

无官方接口，抓取 https://github.com/trending 服务端渲染 HTML。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class GithubTrendingSource(Source):
    name = "github_trending"
    command = "github-trending"
    summary = "GitHub Trending 榜单（HTML）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        from bs4 import BeautifulSoup

        since = ctx.params.get("since", "daily")
        language = ctx.params.get("language", "")

        url = "https://github.com/trending"
        if language:
            url += f"/{language}"
        url += f"?since={since}"

        resp = await http_get(url, ctx=ctx)
        now = datetime.now(timezone.utc)
        soup = BeautifulSoup(resp.text, "html.parser")

        for idx, art in enumerate(soup.select("article.Box-row"), 1):
            repo_link = art.select_one("h2 a")
            if not repo_link:
                continue
            href = (repo_link.get("href") or "").strip("/")
            if "/" not in href:
                continue
            yield RawRecord(
                source=self.name,
                source_id=href,
                content_type="html",
                fetched_at=now,
                data=str(art),
                metadata={"since": since, "language": language, "rank": idx},
            )