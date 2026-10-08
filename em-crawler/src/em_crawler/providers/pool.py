"""涨停/跌停/炸板/昨日涨停池 Provider（push2ex，直连）。"""
from __future__ import annotations

import datetime
import time

import requests as _requests

_UT = "7eea3edcaed734bea9cbfc24409ed989"
_BASE = "https://push2ex.eastmoney.com"
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}

_POOL_PATHS = {"zt": "/getTopicZTPool", "dt": "/getTopicDTPool",
               "zb": "/getTopicZBPool", "yzt": "/getYesterdayZTPool",
               "qs": "/getTopicQSPool", "cx": "/getTopicCXPooll"}
_POOL_SORTS = {"zt": "fbt:asc", "dt": "fund:asc", "zb": "fbt:asc", "yzt": "zdp:desc",
               "qs": "zdp:desc", "cx": "zdp:desc"}

# push2ex 短字段 → 语义名
_FIELD_MAP = {
    "c": "code", "m": "market", "n": "name", "p": "price", "zdp": "pct_change",
    "amount": "amount", "ltsz": "float_mv", "tshare": "total_mv", "hs": "turnover_rate",
    "lbc": "link_count", "fbt": "first_seal_time", "lbt": "last_seal_time",
    "fund": "seal_fund", "zbc": "broke_count", "hybk": "industry", "zttj": "zt_stat",
    "days": "down_days", "zs": "seal_count", "zf": "seal_amount", "ztp": "seal_price",
    "oc": "open_price", "pe": "pe", "fba": "first_seal_time",
    # 强势/次新/炸板池新增字段
    "zdp": "pct_change", "zl": "reason", "kb": "open_board_days", "od": "open_board_date",
    "ipod": "ipo_date", "zttj": "zt_stat", "zf": "amplitude", "vol": "volume",
    "z": "seal_amount", "zb": "broke_count", "hs": "turnover_rate",
}


def pool(client, kind: str, trade_date: str = "", page_size: int = 100, **kw) -> list[dict]:
    d = trade_date.replace("-", "") if trade_date else datetime.date.today().strftime("%Y%m%d")
    params = {"ut": _UT, "dpt": "wz.ztzt", "Pageindex": "0", "pagesize": str(page_size),
              "date": d, "sort": _POOL_SORTS[kind], "_": int(time.time() * 1000)}
    last_err = "rc=102"
    for attempt in range(4):
        try:
            r = _requests.get(_BASE + _POOL_PATHS[kind], params=params, timeout=30, headers=_HEADERS)
            j = r.json()
            if j.get("rc") == 0 and (j.get("data") or {}):
                rows = (j.get("data") or {}).get("pool") or []
                return [_rename(row, d) for row in rows]
            last_err = f"rc={j.get('rc')}"
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
        time.sleep(1.2 * (2 ** attempt))
    return []


def fenbu(client, trade_date: str = "", **kw) -> list[dict]:
    """涨跌分布（涨停板专题顶部分布图）：区间 → 家数。"""
    d = trade_date.replace("-", "") if trade_date else datetime.date.today().strftime("%Y%m%d")
    params = {"ut": _UT, "dpt": "wz.ztzt", "Pageindex": "0", "pagesize": "100",
              "date": d, "_": int(time.time() * 1000)}
    for attempt in range(4):
        try:
            r = _requests.get(_BASE + "/getTopicZDFenBu", params=params, timeout=30, headers=_HEADERS)
            j = r.json()
            data = j.get("data") or {}
            if j.get("rc") == 0 and data:
                out = []
                for item in (data.get("fenbu") or []):
                    for k, v in item.items():
                        out.append({"bucket": k, "count": v})
                return out
        except Exception:
            pass
        time.sleep(1.2 * (2 ** attempt))
    return []


def _rename(row: dict, d: str) -> dict:
    out = {"trade_date": d}
    for k, v in row.items():
        out[_FIELD_MAP.get(k, k)] = v
    return out


ENDPOINTS = {"pool.get": pool, "pool.fenbu": fenbu}