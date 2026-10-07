"""数据中心特殊报表 Provider（需特殊 filter/退避逻辑的报表）。"""
from __future__ import annotations

import datetime as _dt

from em.providers.datacenter import datacenter


def suspend(client, trade_date: str = "", page_size: int = 100, **kw) -> list[dict]:
    """停复牌：filter 必须含 MARKET 与 DATETIME，无数据时前溯最近 14 个交易日。"""
    if trade_date:
        dates = [trade_date]
    else:
        dates = [(_dt.date.today() - _dt.timedelta(days=i)).isoformat() for i in range(14)]
    for d in dates:
        rows = datacenter(client, "RPT_CUSTOM_SUSPEND_DATA_INTERFACE",
                          filter=f'(MARKET="全部")(DATETIME=\'{d}\')',
                          page_size=page_size, page=1)
        if rows:
            return rows
    return []


ENDPOINTS = {"event.suspend": suspend}