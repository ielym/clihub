"""HTTP 工具：标准库实现的带重试 GET。"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
ACCEPT = "text/html,application/xhtml+xml,application/json,*/*;q=0.8"
RETRY_STATUS = (429, 500, 502, 503, 504)


def http_get(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    retries: int = 3,
    backoff: float = 1.0,
    timeout: float = 30.0,
) -> bytes:
    """GET 请求，返回响应体字节；对瞬时错误做指数退避重试。"""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    merged = {"User-Agent": USER_AGENT, "Accept": ACCEPT}
    merged.update(headers or {})

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=merged)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    raise last_exc if last_exc else RuntimeError(f"请求失败: {url}")