"""数据中心通用 Provider：data.eastmoney.com 各 RPT_* 报表。

覆盖领域：财务三表/业绩/资金(龙虎榜/两融/港通/大宗/质押/股东户数)/
F10 JSON 子模块/宏观/数据中心批量事件。统一走 datacenter-web 的 RPT_* 报表。
"""
from __future__ import annotations

import re
from typing import Any

DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DC_REFERER = "https://data.eastmoney.com/"

# 证券类 datacenter（F10 RPT_F10_* 用 securities 域）
SEC_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"


def _get(client, url: str, report: str, filter_: str | None, columns: str,
         page_size: int, page: int, sort_columns: str | None, sort_types: int) -> list[dict]:
    params: dict[str, Any] = {"reportName": report, "columns": columns,
                              "pageSize": page_size, "pageNumber": page}
    if filter_:
        params["filter"] = filter_
    if sort_columns:
        params["sortColumns"] = sort_columns
        params["sortTypes"] = sort_types
    j = client.get_json(url, params=params, referer=DC_REFERER)
    return (j.get("result") or {}).get("data") or []


def datacenter(client, report: str, filter: str | None = None,
               columns: str = "ALL", page_size: int = 10, page: int = 1,
               sort_columns: str | None = None, sort_types: int = -1, **kw) -> list[dict]:
    """通用数据中心报表：返回原始行列表（UPPERCASE 源字段）。

    columns 默认 ALL；个别报表（如 RPT_BLOCKTRADE_OPERATEDEPT_NAME）columns=ALL 会返回空，
    需显式指定字段列表。
    """
    return _get(client, DC_URL, report, filter, columns, page_size, page, sort_columns, sort_types)


def datacenter_board(client, report: str, filter: str | None = None,
                     columns: str = "ALL", page_size: int = 10, page: int = 1,
                     sort_columns: str | None = None, sort_types: int = -1, **kw) -> list[dict]:
    """板块类报表：页面/URL 里板块代码为 BKxxxx（如 BK0475），而报表 BOARD_CODE
    存的是数字编码（BK0475 → 475），此处做归一化后再查。
    """
    if filter:
        filter = re.sub(r'(BOARD_CODE=")BK0*(\d+)"',
                        lambda m: m.group(1) + m.group(2) + '"', filter)
    return _get(client, DC_URL, report, filter, columns, page_size, page, sort_columns, sort_types)


def datacenter_securities(client, report: str, filter: str | None = None,
                          columns: str = "ALL", page_size: int = 10, page: int = 1,
                          sort_columns: str | None = None, sort_types: int = -1, **kw) -> list[dict]:
    """证券类数据中心（RPT_F10_*）。"""
    return _get(client, SEC_URL, report, filter, columns, page_size, page, sort_columns, sort_types)


# 主力数据（机构持仓股）：响应体为 {"data": [...]}，无 result 包装
ZLSJ_URL = "https://data.eastmoney.com/dataapi/zlsj/list"
ZLSJ_REFERER = "https://data.eastmoney.com/zlsj/"


def zlsj_list(client, date: str | None = None, org_type: str = "1", zjc: str = "0",
              sort_field: str = "", sort_direc: str = "1",
              page_size: int = 10, page_num: int = 1, **kw) -> list[dict]:
    """主力数据 · 机构持仓股。org_type 1基金 2QFII 3社保 4券商 5保险 6信托。

    该接口必须带 date，否则返回无序的陈旧数据；未指定时自动取最新报告期。
    """
    if not date:
        date = _latest_report_date(client)
    params: dict[str, Any] = {"date": date, "type": org_type, "zjc": zjc,
                              "sortField": sort_field, "sortDirec": sort_direc,
                              "pageNum": page_num, "pageSize": page_size}
    j = client.get_json(ZLSJ_URL, params=params, referer=ZLSJ_REFERER)
    return j.get("data") or []


def _latest_report_date(client) -> str:
    rows = _get(client, DC_URL, "RPT_MAIN_REPORTDATE", None, "ALL", 1, 1, "REPORT_DATE", -1)
    if rows:
        return str(rows[0].get("REPORT_DATE") or "")[:10]
    return ""


ENDPOINTS = {
    "dc.get": datacenter,
    "dc.board": datacenter_board,
    "dc.securities": datacenter_securities,
    "zlsj.list": zlsj_list,
}