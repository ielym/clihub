"""HTTP 工具：通过快代理隧道代理发请求（stdlib only）。

要点：
- 隧道账号已在 certification.py 取回（绝不硬编码）；这里只负责组代理 URL 与发请求。
- 每次请求新建连接、不复用 keep-alive（隧道"每次请求换 IP"依赖无条件关闭连接）。
- 对瞬时失败做指数退避重试（隧道单次失败是常态，必须重试而非抛异常）。
- 可选锁 IP（--sid，密码后拼接 :<sid> 锁 30 秒）与多通道（kdl-tps-channel 头，仅 http）。
"""
from __future__ import annotations

import gzip
import random
import threading
import time
import urllib.error
import urllib.request
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
ACCEPT = "application/json,text/html,text/plain,*/*;q=0.8"

# 隧道错误码页（tpshttpresponse）：这些是可重试的瞬时失败。
#   440 带宽超限 | 441 请求超频 | 515/516/517 连接目标/代理转发失败
RETRYABLE_TUNNEL = (440, 441, 515, 516, 517)
# 通用可重试状态码
RETRYABLE_HTTP = (408, 429, 500, 502, 503, 504)


def build_proxy_url(cred: dict, sid: Optional[str] = None) -> str:
    """组代理 URL。sid 非空时锁定该 IP 30 秒（password:sid，Unix 的 URL 需 quote）。"""
    password = cred["password"]
    if sid:
        password = f"{password}:{sid}"
    user = urllib.request.quote(cred["username"], safe="")
    pwd = urllib.request.quote(password, safe="")
    return f"http://{user}:{pwd}@{cred['tunnel']}/"


class TokenBucket:
    """令牌桶速率限制：令牌按 rate/s 补充，容量封顶，支持并发而安全。"""

    def __init__(self, rate: float, capacity: Optional[float] = None):
        self.rate = max(1.0, float(rate) or 1.0)
        self.capacity = capacity if capacity is not None else self.rate
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, n: int = 1):
        n = max(1, int(n))
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                wait = (n - self.tokens) / self.rate
            time.sleep(wait)


# 进程级共享速率限制器；默认 5 次/s（请求排队，即超带宽/超频时排队而非丢弃）
_SHARED_BUCKET = None
_BUCKET_LOCK = threading.Lock()


def rate_limiter(rate: float) -> TokenBucket:
    global _SHARED_BUCKET
    with _BUCKET_LOCK:
        if _SHARED_BUCKET is None or (rate and abs(_SHARED_BUCKET.rate - rate) > 1e-9):
            _SHARED_BUCKET = TokenBucket(rate, capacity=max(5, int(rate)))
        return _SHARED_BUCKET


def _is_retriable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP or exc.code in RETRYABLE_TUNNEL
    # 连接失败 / 隧道 CONNECT 失败 / 超时等
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return True
    return False


def http_request(
    method: str,
    url: str,
    *,
    cred: dict,
    sid: Optional[str] = None,
    channel: Optional[str] = None,
    headers: Optional[dict] = None,
    data: Optional[str] = None,
    retries: int = 3,
    backoff: float = 1.0,
    timeout: float = 30.0,
    rate: Optional[float] = None,
) -> dict:
    """通过隧道发起请求，返回结果字典。

    每次调用采集并消费 1 个令牌（默认 5 次/s）。对可重试瞬时失败做指数退避重试。
    结果字段：
        status      HTTP 状态码（网络层失败为 None，仅 intermediate 阶段）
        ok         是否最终成功
        body       响应体字节（成功时）；gzip 自动解压
        reason     HTTPError 原因（失败时）
        attempts   实际尝试次数
        elapsed_ms 单次请求耗时（毫秒）
    """
    # 实现细节：本函数定位为可被并发调用的底层接口，令牌采集与重试在此完成。
    limiter = rate_limiter(float(rate) if rate else float(cred.get("rate_limit_per_sec", 5)))
    limiter.acquire(1)

    proxy = build_proxy_url(cred, sid)
    handlers = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(handlers)

    merged = {"User-Agent": USER_AGENT, "Accept": ACCEPT, "Accept-Encoding": "gzip"}
    if channel:
        # 指定通道（只支持 http；https 隧道会忽略该头）
        merged["kdl-tps-channel"] = str(channel)
    merged.update(headers or {})

    body = data.encode("utf-8") if isinstance(data, str) else data

    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        req = urllib.request.Request(url, data=body, method=method, headers=merged)
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return {
                    "status": resp.status,
                    "ok": True,
                    "body": raw,
                    "reason": None,
                    "attempts": attempt + 1,
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                }
        except Exception as e:  # noqa: BLE001 统一捕获并按可重试性处理
            last_exc = e
            if _is_retriable(e) and attempt < retries:
                # 指数退避 + jitter，避免多个重试同时击穿
                time.sleep(backoff * (2 ** attempt) + random.uniform(0, 0.5))
                continue
            break

    # 失败：把 HTTPError 转成信息更友好的失败结果
    reason = _describe_error(last_exc)
    status = None
    if isinstance(last_exc, urllib.error.HTTPError):
        status = last_exc.code
    return {
        "status": status,
        "ok": False,
        "body": None,
        "reason": reason,
        "attempts": retries + 1,
        "elapsed_ms": None,
    }


def _describe_error(exc: Optional[Exception]) -> str:
    if exc is None:
        return "未知错误"
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        # 隧道 CONNECT 失败会报 "Tunnel connection failed: <code> ..."
        msg = str(exc.reason)
        return f"连接失败：{msg}"
    return f"{type(exc).__name__}: {exc}"