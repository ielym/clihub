"""宏观 Provider：国内/海外指标 + 行业/概念板块。"""
from __future__ import annotations

import json
import re
import time
from html import unescape

DOMESTIC_REPORTS = {
    "cpi": "RPT_ECONOMY_CPI", "ppi": "RPT_ECONOMY_PPI", "pmi": "RPT_ECONOMY_PMI",
    "gdp": "RPT_ECONOMY_GDP", "house_price": "RPT_ECONOMY_HOUSE_PRICE",
    "m2": "RPT_ECONOMY_CURRENCY_SUPPLY", "lpr": "RPTA_WEB_RATE", "fiscal": "RPT_ECONOMY_INCOME",
    # P2-a 补全：企业景气/工业增加值/海关进出口/外汇与黄金储备/房价指数/货币供应量全口径
    "business_climate": "RPT_ECONOMY_BOOM_INDEX",
    "industrial_va": "RPT_ECONOMY_INDUS_GROW",
    "trade": "RPT_ECONOMY_CUSTOMS",
    "gold_reserve": "RPT_ECONOMY_GOLD_CURRENCY",
    "forex_reserve": "RPT_ECONOMY_GOLD_CURRENCY",
    "house_index": "RPT_ECONOMY_HOSE_INDEX",
    "money_supply": "RPT_ECONOMY_CURRENCY_SUPPLY",
}
HTML_PAGES = {
    "shzr": "https://data.eastmoney.com/cjsj/shzr.html",
    "electricity": "https://data.eastmoney.com/cjsj/ndydl.html",
}
_VALUE_FIELD = {
    "m2": "CURRENCY_SAME", "lpr": "LPR1Y", "fiscal": "NATIONAL_SAME",
    "business_climate": "BOOM_INDEX", "industrial_va": "BASE_SAME",
    "trade": "EXIT_BASE_SAME", "gold_reserve": "GOLD_RESERVES",
    "forex_reserve": "FOREX", "house_index": "HOSE_INDEX",
    "money_supply": "BASIC_CURRENCY_SAME",
}
# 宏观/行业指标库（/cjsj/hyzs.html 内嵌的数百个指标，报表 RPT_INDUSTRY_INDEX）
INDICATOR_REPORT = "RPT_INDUSTRY_INDEX"


def macro_domestic(client, indicator: str, page_size: int = 5, **kw) -> list[dict]:
    key = indicator.lower()
    if key in HTML_PAGES:
        return _html_macro(client, key, page_size)
    report = DOMESTIC_REPORTS.get(key, indicator)
    rows = _dc(client, report, page_size, "REPORT_DATE", key == "lpr")
    value_field = _VALUE_FIELD.get(key, "NATIONAL_SAME")
    date_field = "TRADE_DATE" if key == "lpr" else "REPORT_DATE"
    out = []
    for r in rows:
        out.append({"region": "CN", "indicator": key,
                    "report_date": r.get(date_field), "period": r.get("TIME"),
                    "value": r.get(value_field), **r})
    return out


def macro_indicator_list(client, page_size: int = 1000, **kw) -> list[dict]:
    """宏观/行业指标库全量清单（每个指标的当期值/涨跌与所属板块）。"""
    return _dc(client, INDICATOR_REPORT, page_size, "", False,
               filter_='(IS_NEWEST="True")')


def macro_indicator_history(client, indicator_id: str, page_size: int = 60, **kw) -> list[dict]:
    """单个宏观/行业指标的历史序列（indicator_id 取自 macro_indicator_list）。"""
    return _dc(client, INDICATOR_REPORT, page_size, "REPORT_DATE", False,
               filter_=f'(INDICATOR_ID="{indicator_id}")')


def macro_overseas(client, economy: str = "USANEW", page_size: int = 5, **kw) -> list[dict]:
    rows = _dc(client, f"RPT_ECONOMICVALUE_{economy}", page_size, "REPORT_DATE", False)
    return [{"region": economy, "indicator": r.get("INDICATOR_NAME"), **r} for r in rows]


def _dc(client, report, page_size, sort_columns, use_jsonp, filter_=None):
    if use_jsonp:
        return _jsonp(client, report, page_size)
    params = {"reportName": report, "columns": "ALL", "pageSize": page_size,
              "pageNumber": 1, "source": "WEB", "client": "WEB"}
    if sort_columns:
        params["sortColumns"] = sort_columns
        params["sortTypes"] = -1
    if filter_:
        params["filter"] = filter_
    j = client.get_json("https://datacenter-web.eastmoney.com/api/data/v1/get",
                        params=params, referer="https://data.eastmoney.com/")
    return (j.get("result") or {}).get("data") or []


def _jsonp(client, report, page_size):
    cb = f"jQuery_{int(time.time() * 1000)}"
    url = (f"https://datacenter-web.eastmoney.com/api/data/v1/get?callback={cb}"
           f"&reportName={report}&columns=ALL&pageSize={page_size}&pageNumber=1"
           f"&sortColumns=TRADE_DATE&sortTypes=-1&source=WEB&client=WEB")
    text = client.get_text(url, referer="https://data.eastmoney.com/cjsj/globalRateLPR.html")
    try:
        return (json.loads(text[text.index("(") + 1:text.rindex(")")]).get("result") or {}).get("data") or []
    except Exception:
        return []


def _html_macro(client, key, page_size):
    url = HTML_PAGES[key]
    html = client.get_text(url, referer="https://data.eastmoney.com/cjsj/")
    rows = []
    m = re.search(r'var\s+data\s*=\s*(\[.*?\]);', html, re.S) or re.search(r'"data"\s*:\s*(\[.*?\])', html, re.S)
    if m:
        try:
            d = json.loads(m.group(1))
            rows = [x for x in d if isinstance(x, dict)]
        except (ValueError, TypeError):
            pass
    if not rows:
        tm = re.search(r'<table[^>]*>(.*?)</table>', html, re.S)
        if tm:
            for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tm.group(1), re.S):
                tds = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)
                cells = [re.sub(r"<[^>]+>", "", unescape(t)).strip() for t in tds]
                if len(cells) >= 2:
                    rows.append({"report_date": cells[0], "value": cells[1]})
    return [{"region": "CN", "indicator": key, **r} for r in rows[:page_size]]


ENDPOINTS = {
    "macro.domestic": macro_domestic,
    "macro.overseas": macro_overseas,
    "macro.indicator_list": macro_indicator_list,
    "macro.indicator_history": macro_indicator_history,
}