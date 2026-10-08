"""资金流向 Provider：push2 个股资金流 kline（主力/大单/中单/小单净额）。"""
from __future__ import annotations

from typing import Any

from em_crawler.providers import _secid

FFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
_REFERER = "https://quote.eastmoney.com/"

# fflow 字段：时间,主力净额,小单净额,中单净额,大单净额,超大单净额,...
_FFLOW_KEYS = ["date", "main_net", "small_net", "mid_net", "large_net", "super_net",
               "main_pct", "small_pct", "mid_pct", "large_pct", "super_pct",
               "close", "pct_change"]


def moneyflow(client, code: str = "", lmt: int = 5, secid: str = "", **kw) -> list[dict[str, Any]]:
    """个股/指数资金流历史。传 secid（如 1.000001）则按指数口径，否则由 code 推断。"""
    j = client.get_json(FFLOW_URL,
                        params={"lmt": lmt, "klt": 101, "secid": secid or _secid(code),
                                "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63"},
                        referer=_REFERER)
    data = j.get("data") or {}
    klines = data.get("klines") or []
    out = []
    for line in klines:
        p = line.split(",")
        if len(p) < 13:
            continue
        out.append({k: (_f(p[i]) if i >= 1 else p[i]) for i, k in enumerate(_FFLOW_KEYS) if i < len(p)})
    return out


def _f(v):
    try:
        return float(v) if v not in ("", "-", None) else None
    except (TypeError, ValueError):
        return None


ENDPOINTS = {"money.flow": moneyflow}