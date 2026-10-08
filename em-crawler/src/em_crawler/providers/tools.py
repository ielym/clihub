"""工具 Provider：诊断 / 选股 / 主力监控 / 指数估值 / 定投计算 / 回测 / 互动。"""
from __future__ import annotations

import re

QA_REFERER = "https://guba.eastmoney.com/"


def stock_diagnosis(client, code: str, **kw) -> dict:
    """个股诊断简易评分（0-100），综合股东集中度+行业地位+市值规模。"""
    secucode = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
    from em_crawler.providers.datacenter import datacenter
    ind = datacenter(client, "RPT_STOCK_INDUSTRY_STA", filter=f'(SECURITY_CODE="{code}")',
                     page_size=1, page=1) or []
    mkt = datacenter(client, "RPT_STOCK_MARKET_STA", filter=f'(SECURITY_CODE="{code}")',
                     page_size=1, page=1) or []
    holder = datacenter(client, "RPT_HOLDERNUM_DET", filter=f'(SECURITY_CODE="{code}")',
                        page_size=1, page=1, sort_columns="END_DATE") or []
    ind0, mkt0, h0 = (ind[0] if ind else {}), (mkt[0] if mkt else {}), (holder[0] if holder else {})
    score = 50.0
    if h0.get("HOLDER_NUM_RATIO") is not None:
        score += max(-15, min(15, float(h0["HOLDER_NUM_RATIO"]) * 2))
    if ind0.get("TOTAL_MARKET_CAP"):
        try:
            c = float(ind0["TOTAL_MARKET_CAP"])
            score += 10 if c > 1e11 else (5 if c > 1e10 else 0)
        except (TypeError, ValueError):
            pass
    score = max(0, min(100, score))
    return {"code": code, "secucode": secucode, "diagnosis_score": round(score, 1),
            "diagnosis_level": ("A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"),
            "industry_rank": ind0, "market_stat": mkt0, "holder_change": h0}


def main_monitor(client, page_size: int = 20, **kw) -> list[dict]:
    from em_crawler.providers.quote import clist
    return clist(client, "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                 fields="f2,f3,f12,f14,f62,f184,f185,f186,f187,f188",
                 page_size=page_size)


def index_valuation(client, **kw) -> list[dict]:
    from em_crawler.providers.quote import SNAPSHOT_URL
    indices = [("1.000001", "上证指数"), ("0.399001", "深证成指"), ("0.399006", "创业板指"),
               ("1.000300", "沪深300"), ("1.000016", "上证50"), ("1.000905", "中证500")]
    out = []
    for secid, name in indices:
        j = client.get_json(SNAPSHOT_URL,
                            params={"secid": secid, "fields": "f43,f57,f58,f9,f23,f116,f117,f162", "fltt": 2, "invt": 2},
                            referer="https://quote.eastmoney.com/")
        d = j.get("data") or {}
        if d:
            out.append({"index_code": secid, "index_name": name, "price": d.get("f43"),
                        "pb": d.get("f9"), "pe_ttm": d.get("f23"),
                        "total_mv": d.get("f116"), "circ_mv": d.get("f117"), "pe": d.get("f162")})
    return out


def fund_calculator(client, fund_code: str, monthly_amount: float = 1000.0,
                     months: int = 12, annual_rate: float = 0.08, **kw) -> dict:
    r = annual_rate / 12
    if r == 0:
        fv, tp = monthly_amount * months, 0.0
    else:
        fv = monthly_amount * ((1 + r) ** months - 1) / r * (1 + r)
        tp = fv - monthly_amount * months
    return {"fund_code": fund_code, "monthly_amount": monthly_amount, "months": months,
            "annual_rate": annual_rate, "future_value": round(fv, 2),
            "total_invest": round(monthly_amount * months, 2),
            "total_profit": round(tp, 2),
            "profit_ratio": round(tp / (monthly_amount * months) * 100, 2) if monthly_amount else 0}


def portfolio_backtest(client, weights=None, period_returns=None, **kw) -> dict:
    if isinstance(weights, (list, tuple)):
        weights = {f"P{i + 1}": float(w) for i, w in enumerate(weights)}
    if isinstance(period_returns, (list, tuple)):
        period_returns = {f"P{i + 1}": float(r) for i, r in enumerate(period_returns)}
    weights = weights or {}
    period_returns = period_returns or {}
    total = sum(weights.values())
    ret = 0.0
    detail = {}
    for code, w in weights.items():
        rr = period_returns.get(code, 0.0)
        contrib = (w / total) * rr if total else 0.0
        ret += contrib
        detail[code] = {"weight": w, "return": rr, "contribution": contrib}
    return {"weights": weights, "total_weight": total,
            "portfolio_return": round(ret, 6),
            "annualized_return": round((1 + ret) - 1, 6), "detail": detail}


def interactive(client, code: str, page_size: int = 10, **kw) -> list[dict]:
    html = client.get_text("https://guba.eastmoney.com/qa/qa_search.aspx",
                           params={"company": code, "qatype": 1}, referer=QA_REFERER)
    from em_crawler.providers.guba import _var_json
    data = _var_json(html, "qa_list") or {}
    out = []
    for r in (data.get("re") or [])[:page_size]:
        out.append({"code": code, "post_id": r.get("post_id"),
                    "question": r.get("ask_question") or "",
                    "answer": r.get("ask_answer") or "",
                    "publish_time": r.get("post_publish_time"),
                    "reply_time": r.get("post_display_time"),
                    "stock_name": r.get("stockbar_name")})
    return out


def finance_infographic(client, code: str, **kw) -> dict:
    secu = f"{'SH' if code.startswith('6') else 'SZ'}{code}"
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={secu}"
    html = client.get_text(url, referer="https://emweb.securities.eastmoney.com/")
    from em_crawler.providers.fund import _parse_tables
    return {"code": code, "url": url, "html_len": len(html), "tables": _parse_tables(html)}


ENDPOINTS = {
    "tool.diagnosis": stock_diagnosis,
    "tool.main_monitor": main_monitor,
    "tool.index_valuation": index_valuation,
    "tool.fund_calc": fund_calculator,
    "tool.backtest": portfolio_backtest,
    "tool.interactive": interactive,
    "tool.finance_infographic": finance_infographic,
}