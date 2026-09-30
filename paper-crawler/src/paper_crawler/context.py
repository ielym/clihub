"""抓取上下文与 HTTP 工具。"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
ACCEPT = "application/json,text/html,application/xhtml+xml,application/xml,*/*;q=0.8"


@dataclass
class RateLimitConfig:
    """请求重试配置。"""

    retry_times: int = 3
    retry_backoff: float = 1.0  # 指数退避基数（秒）


@dataclass
class FetchContext:
    """抓取上下文，传递给数据源 fetch()。"""

    params: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, str] = field(default_factory=dict)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    errors: list[str] = field(default_factory=list)

    def record_error(self, message: str) -> None:
        """记录致命抓取错误：写入 errors 并打印到 stderr，最终使进程返回非 0。"""
        self.errors.append(message)
        print(f"[error] {message}", file=sys.stderr)

    def warn(self, message: str) -> None:
        """记录非致命问题：仅打印到 stderr，不影响退出码。"""
        print(f"[warn] {message}", file=sys.stderr)


async def http_get(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    ctx: Optional[FetchContext] = None,
) -> "httpx.Response":
    """带重试与指数退避的 GET 请求。"""
    import httpx

    rl = ctx.rate_limit if ctx else RateLimitConfig()
    merged = dict(headers or {})
    merged.setdefault("User-Agent", USER_AGENT)
    merged.setdefault("Accept", ACCEPT)

    last_exc: Optional[Exception] = None
    resp: Optional[httpx.Response] = None
    for attempt in range(rl.retry_times + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=merged)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(rl.retry_backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ) as e:
            last_exc = e
            if attempt < rl.retry_times:
                await asyncio.sleep(rl.retry_backoff * (2 ** attempt))
                continue
            raise

    if last_exc:
        raise last_exc
    if resp is None:
        raise RuntimeError(f"请求未返回响应: {url}")
    return resp