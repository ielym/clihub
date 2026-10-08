"""跨市场 Provider：全球指数 / 债券 / 北交所 / 跨市场快照。"""
from __future__ import annotations

from em_crawler.providers.quote import clist, snapshot

MARKET_LABEL = {
    "100": "HK_INDEX", "116": "HK", "105": "NASDAQ", "106": "NYSE", "107": "AMEX",
    "119": "FOREX", "118": "GOLD", "113": "COMMODITY_FUTURE", "8": "FIN_FUTURE",
    "0": "SZ", "1": "SH",
}


def global_index(client, page_size: int = 100, **kw) -> list[dict]:
    rows = clist(client, "m:100", page_size=page_size)
    secids = [f"{r.get('market','')}.{r.get('code','')}" for r in rows if r.get("code")]
    out = []
    for i in range(0, len(secids), 50):
        j = client.get_json("https://push2.eastmoney.com/api/qt/ulist.np/get",
                            params={"secids": ",".join(secids[i:i + 50]), "fltt": 2, "invt": 2,
                                    "fields": "f2,f3,f12,f13,f14,f15,f16,f17,f18,f20"},
                            referer="https://quote.eastmoney.com/")
        for it in (j.get("data") or {}).get("diff") or []:
            mkt = str(it.get("f13", ""))
            out.append({"secid": f"{mkt}.{it.get('f12')}", "code": str(it.get("f12")),
                        "name": it.get("f14"), "price": it.get("f2"), "pct_change": it.get("f3"),
                        "high": it.get("f15"), "low": it.get("f16"), "open": it.get("f17"),
                        "pre_close": it.get("f18"), "amount": it.get("f20"),
                        "market": mkt, "market_label": MARKET_LABEL.get(mkt, mkt)})
    return out


def bond_list(client, page_size: int = 20, **kw) -> list[dict]:
    return clist(client, "m:0+t:8,m:1+t:8", page_size=page_size)


def bj_stock(client, page_size: int = 20, **kw) -> list[dict]:
    return clist(client, "m:0+t:81+s:2048", page_size=page_size)


def cross_snapshot(client, secid: str, **kw) -> dict:
    # 跨市场快照：直接按 secid 取（复用 quote.snapshot 需要 code，这里用 secid 直查）
    j = client.get_json("https://push2.eastmoney.com/api/qt/stock/get",
                        params={"secid": secid, "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170",
                                "fltt": 2, "invt": 2},
                        referer="https://quote.eastmoney.com/")
    d = j.get("data") or {}
    return {"secid": secid, "code": d.get("f57"), "name": d.get("f58"),
            "price": d.get("f43"), "high": d.get("f44"), "low": d.get("f45"),
            "open": d.get("f46"), "pre_close": d.get("f60"), "volume": d.get("f47"),
            "amount": d.get("f48"), "pct_change": d.get("f170"), "change": d.get("f169"),
            "pe_dynamic": d.get("f162"), "pb": d.get("f167"), "turnover_rate": d.get("f168"),
            "total_mv": d.get("f116"), "float_mv": d.get("f117")}


ENDPOINTS = {
    "cross.global_index": global_index,
    "cross.bond": bond_list,
    "cross.bj": bj_stock,
    "cross.snapshot": cross_snapshot,
}