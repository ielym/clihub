"""统一 HTTP 客户端：后端自选（push2 走 curl_cffi 指纹仿真，其余 httpx）+ 代理 + 限速重试。"""
from __future__ import annotations

import os
import random
import time
from typing import Any
from urllib.parse import urlparse

import httpx

_IMPERSONATE_HOSTS = {"push2.eastmoney.com", "push2delay.eastmoney.com",
                      "push2his.eastmoney.com", "push2ex.eastmoney.com"}

_UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def resolve_proxies(explicit: dict | None = None) -> dict | None:
    if explicit:
        return explicit
    single = os.environ.get("EM_PROXY", "").strip()
    if single:
        return {"http": single, "https": single}
    http_p = os.environ.get("HTTP_PROXY", "").strip() or os.environ.get("http_proxy", "").strip()
    https_p = (os.environ.get("HTTPS_PROXY", "").strip()
               or os.environ.get("https_proxy", "").strip()
               or os.environ.get("ALL_PROXY", "").strip()
               or os.environ.get("all_proxy", "").strip())
    if not http_p and not https_p:
        return None
    return {"http": http_p or https_p, "https": https_p or http_p}


class HttpClient:
    def __init__(self, timeout: float | None = None, max_retry: int = 3,
                 proxies: dict | None = None):
        if timeout is None:
            timeout = float(os.environ.get("EM_HTTP_TIMEOUT", "30"))
        self.timeout = timeout
        self.max_retry = max_retry
        self.proxies = resolve_proxies(proxies)
        self.verify = os.environ.get("EM_VERIFY_TLS", "1") != "0"
        self._httpx = httpx.Client(
            verify=self.verify, timeout=self.timeout, follow_redirects=True,
            proxy=(self.proxies.get("https") or self.proxies.get("http")) if self.proxies else None,
        )
        self._ccffi = None
        self._cooldown: dict[str, float] = {}
        self._last: dict[str, float] = {}

    def _backend(self, url: str) -> str:
        host = urlparse(url).hostname or ""
        if host in _IMPERSONATE_HOSTS:
            if self._ccffi is None:
                from curl_cffi import requests as _cc
                self._ccffi = _cc
            return "curl_cffi"
        return "httpx"

    def _headers(self, referer: str, extra: dict | None = None) -> dict:
        h = {
            "User-Agent": random.choice(_UA_POOL),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer,
        }
        if extra:
            h.update(extra)
        return h

    def _throttle(self, domain: str) -> None:
        now = time.monotonic()
        wait = random.uniform(0.2, 0.8)
        elapsed = now - self._last.get(domain, 0.0)
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self._last[domain] = time.monotonic()

    def get_text(self, url: str, params: dict | None = None,
                 referer: str = "https://quote.eastmoney.com/",
                 headers: dict | None = None) -> str:
        return self._request(url, params, referer, headers, as_json=False)

    def get_json(self, url: str, params: dict | None = None,
                 referer: str = "https://quote.eastmoney.com/",
                 headers: dict | None = None) -> Any:
        return self._request(url, params, referer, headers, as_json=True)

    def _request(self, url, params, referer, headers, as_json):
        domain = urlparse(url).hostname or url
        last_err: Exception | None = None
        for attempt in range(self.max_retry):
            until = self._cooldown.get(domain, 0.0)
            wait = until - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._throttle(domain)
            try:
                body = self._do(url, params, referer, headers)
            except Exception as e:
                last_err = e
                s = f"{type(e).__name__} {e}".lower()
                if any(k in s for k in ("connection", "closed", "reset", "curl", "remote")):
                    self._cooldown[domain] = time.monotonic() + 2.0
                time.sleep(min(2.0 ** attempt, 6.0))
                continue
            if isinstance(body, str):
                if body == "":
                    last_err = RuntimeError("empty body")
                    continue
                if as_json:
                    try:
                        import json as _json
                        return _json.loads(body)
                    except Exception:
                        return body
                return body
            return body
        raise RuntimeError(f"request failed after {self.max_retry} retries: {url} ({last_err})")

    def _do(self, url, params, referer, headers):
        backend = self._backend(url)
        h = self._headers(referer, headers)
        if backend == "curl_cffi":
            kwargs: dict[str, Any] = {
                "params": params, "headers": h, "impersonate": "chrome124",
                "verify": self.verify, "timeout": self.timeout,
            }
            if self.proxies:
                kwargs["proxies"] = self.proxies
            r = self._ccffi.get(url, **kwargs)
            if r.status_code >= 400:
                r.raise_for_status()
            return r.text
        r = self._httpx.get(url, params=params, headers=h)
        if r.status_code >= 400:
            r.raise_for_status()
        return r.text

    def close(self) -> None:
        self._httpx.close()
        self._ccffi = None