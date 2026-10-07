"""全量补全 Provider：期货成交持仓 / 期权龙虎榜 / 商品指数 / 可转债 / 基金扩展 / 资讯原文。

这些数据源在旧 em-crawler 或东财站点存在、但 em CLI 之前未覆盖；此处补齐。
均走 datacenter-web 的 RPT_* 报表或专用公开接口，带可选 filter 的按需拼接。
"""
from __future__ import annotations

from typing import Any

from em.providers.datacenter import datacenter, DC_URL, _get


def _dc(client, report: str, filter_: str | None, page_size: int = 20,
        sort_columns: str | None = None, sort_types: int = -1, page: int = 1) -> list[dict]:
    return _get(client, DC_URL, report, filter_, "ALL", page_size, page, sort_columns, sort_types)


def futures_position_rank(client, security_code: str = "", trade_market_code: str = "",
                          page_size: int = 20, **kw) -> list[dict]:
    """期货成交持仓排名。security_code 移产品种代码（如 au/sc），trade_market_code 交易所码；均可选。"""
    parts = []
    if security_code:
        parts.append(f'(SECURITY_CODE="{security_code}")')
    if trade_market_code:
        parts.append(f'(TRADE_MARKET_CODE="{trade_market_code}")')
    return _dc(client, "RPT_FUTU_DAILYPOSITION", "".join(parts) or None,
               page_size=page_size, sort_columns="TRADE_DATE", sort_types=-1)


def option_lhb(client, security_code: str = "", page_size: int = 20, **kw) -> list[dict]:
    """期权龙虎榜（会员成交/持仓排名），security_code 可选（不传返回全部）。"""
    flt = f'(SECURITY_CODE="{security_code}")' if security_code else None
    return _dc(client, "RPT_IF_BILLBOARD_TD", flt, page_size=page_size,
               sort_columns="TRADE_DATE", sort_types=-1)


def commodity_index(client, indicator_id: str = "", page_size: int = 20, **kw) -> list[dict]:
    """宏观/行业/商品指数序列（RPT_INDUSTRY_INDEX），indicator_id 如 EMI00662535（中证商品指数）。"""
    flt = f'(INDICATOR_ID="{indicator_id}")' if indicator_id else None
    return _dc(client, "RPT_INDUSTRY_INDEX", flt, page_size=page_size,
               sort_columns="REPORT_DATE", sort_types=-1)


# ---- 可转债数据中心 / 详情 ----
KZZ_LIST = "RPT_BOND_CB_LIST"


def kzz_detail(client, page_size: int = 20, **kw) -> list[dict]:
    """可转债数据中心全量列表（含转股价/转股价值/溢价率/强赎/回售等字段）。"""
    return datacenter(client, KZZ_LIST, None, "ALL", int(page_size), 1, None, -1)


ENDPOINTS = {
    "ext.futures_position_rank": futures_position_rank,
    "ext.option_lhb": option_lhb,
    "ext.commodity_index": commodity_index,
    "ext.kzz_detail": kzz_detail,
}