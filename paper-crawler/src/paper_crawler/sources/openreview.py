"""OpenReview 数据源。

接口：https://api2.openreview.net （v2 REST）
notes 端点需要认证，未提供凭据时返回空。
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord


class OpenReviewSource(Source):
    name = "openreview"
    command = "openreview"
    summary = "OpenReview 投稿/评审（API v2，需凭据）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    def _auth_headers(self, ctx: FetchContext) -> dict:
        token = ctx.credentials.get("token") or ctx.credentials.get("openreview_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
        username = ctx.credentials.get("username")
        password = ctx.credentials.get("password")
        if username and password:
            cred = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {cred}"}
        return {}

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        venue_id = ctx.params.get("venue_id", "ICLR.cc/2024/Conference")
        status = ctx.params.get("status", "accepted")
        limit = int(ctx.params.get("limit", 100))
        offset = int(ctx.params.get("offset", 0))
        headers = self._auth_headers(ctx)

        # 先读取 venue group，取得 submission_name
        submission_name = "Submission"
        try:
            group_resp = await http_get(
                f"https://api2.openreview.net/groups/{venue_id}", headers=headers, ctx=ctx
            )
            group_data = group_resp.json()
            groups = group_data.get("groups", [group_data]) if isinstance(group_data, dict) else []
            if groups:
                content = groups[0].get("content", {})
                submission_name = content.get("submission_name", {}).get("value", "Submission")
        except Exception as e:
            ctx.warn(f"openreview venue group 读取失败，回退默认 submission 名：{type(e).__name__}: {e}")

        params = {"invitation": f"{venue_id}/-/{submission_name}", "limit": limit, "offset": offset}
        try:
            resp = await http_get(
                "https://api2.openreview.net/notes", params=params, headers=headers, ctx=ctx
            )
            data = resp.json()
        except Exception as e:
            ctx.record_error(f"openreview notes 抓取失败：{type(e).__name__}: {e}")
            return

        notes = data.get("notes", [])
        now = datetime.now(timezone.utc)
        for note in notes:
            nid = note.get("id")
            if not nid:
                continue
            yield RawRecord(
                source=self.name,
                source_id=nid,
                content_type="json",
                fetched_at=now,
                data=note,
                metadata={"venue_id": venue_id, "status": status},
            )