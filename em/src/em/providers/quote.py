"""行情 Provider：push2 快照 / K线 / 分时 / 盘口 / 榜单。

provider 输出语义字段 dict（不是 push2 的 f 字段），metric 目录引用这些语义字段。
"""
from __future__ import annotations

from typing import Any

from em.providers import _secid, _market

SNAPSHOT_URL = "https://push2.eastmoney.com/api/qt/stock/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TRENDS_URL = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"

_REFERER = "https://quote.eastmoney.com/"

# push2 快照 f 字段 → 语义名
_SNAP_FIELDS = {
    "f43": "price", "f44": "high", "f45": "low", "f46": "open",
    "f47": "volume", "f48": "amount", "f50": "volume_ratio", "f51": "limit_up",
    "f52": "limit_down", "f57": "code", "f58": "name", "f60": "pre_close",
    "f116": "total_mv", "f117": "float_mv", "f162": "pe_dynamic",
    "f163": "pe_static", "f164": "pe_ttm", "f167": "pb", "f168": "turnover_rate",
    "f169": "change", "f170": "pct_change", "f171": "amplitude",
    "f184": "main_net_inflow", "f185": "small_net_inflow",
    "f186": "mid_net_inflow", "f187": "large_net_inflow", "f188": "super_net_inflow",
    "f104": "up_count", "f105": "down_count", "f106": "flat_count",
}


def snapshot(client, code: str, **kw) -> dict[str, Any]:
    j = client.get_json(SNAPSHOT_URL,
                        params={"secid": _secid(code),
                                "fields": ",".join(_SNAP_FIELDS.keys()),
                                "fltt": 2, "invt": 2},
                        referer=_REFERER)
    d = j.get("data") or {}
    out = {}
    for f, semantic in _SNAP_FIELDS.items():
        if f in d:
            out[semantic] = d[f]
    return out


_ADJUST = {0: "none", 1: "qfq", 2: "hfq"}
_REV_ADJUST = {"none": 0, "qfq": 1, "hfq": 2}


def kline(client, code: str, klt: int = 101, fqt: int = 0,
          lmt: int = 1, end: str = "", **kw) -> list[dict[str, Any]]:
    """K线：返回 list[{date,open,close,high,low,volume,amount,...}]（升序）。"""
    params = {"secid": _secid(code), "klt": klt, "fqt": fqt,
              "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
              "lmt": lmt, "end": (end or "20500101")}
    j = client.get_json(KLINE_URL, params=params, referer=_REFERER)
    data = j.get("data") or {}
    klines = data.get("klines") or []
    out = []
    for line in klines:
        p = line.split(",")
        if len(p) < 11:
            continue
        # p: date,open,close,high,low,volume,amount,amplitude,pct_change,change,turnover_rate
        out.append({
            "date": p[0], "open": _num(p[1]), "close": _num(p[2]),
            "high": _num(p[3]), "low": _num(p[4]), "volume": _num(p[5]),
            "amount": _num(p[6]), "amplitude": _num(p[7]),
            "pct_change": _num(p[8]), "change": _num(p[9]),
            "turnover_rate": _num(p[10]),
        })
    return out


def trends(client, code: str, ndays: int = 1, **kw) -> list[dict[str, Any]]:
    j = client.get_json(TRENDS_URL,
                        params={"secid": _secid(code), "ndays": ndays, "iscr": "0",
                                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58"},
                        referer=_REFERER)
    data = j.get("data") or {}
    name = data.get("name", "")
    rows = []
    for line in (data.get("trends") or []):
        p = line.split(",")
        if len(p) < 8:
            continue
        rows.append({"name": name, "time": p[0], "price": _num(p[2]),
                     "high": _num(p[3]), "low": _num(p[4]),
                     "volume": _num(p[5]), "amount": _num(p[6]),
                     "avg_price": _num(p[7])})
    return rows


def orderbook(client, code: str, **kw) -> dict[str, Any]:
    fields = ",".join([f"f{i}" for i in range(21, 41)] + ["f43", "f57", "f58", "f60"])
    j = client.get_json(SNAPSHOT_URL,
                        params={"secid": _secid(code), "fields": fields, "fltt": 2, "invt": 2},
                        referer=_REFERER)
    d = j.get("data") or {}
    out: dict[str, Any] = {"code": d.get("f57"), "name": d.get("f58"),
                           "price": d.get("f43"), "pre_close": d.get("f60")}
    for i in range(1, 6):
        out[f"bid_{i}_price"] = d.get(f"f{20 + i}")
        out[f"bid_{i}_volume"] = d.get(f"f{30 + i}")
        out[f"ask_{i}_price"] = d.get(f"f{20 + 10 + i}")
        out[f"ask_{i}_volume"] = d.get(f"f{30 + 10 + i}")
    return out


def clist(client, fs: str, fields: str = "", rename: dict | None = None,
          fid: str = "f3", po: int = 1, page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """push2 clist 通用榜单：fields 显式指定 + rename 映射为语义名。

    - 不传 fields → 默认行情字段集（兼容旧用法）。
    - 不传 rename → 用内置 _CLIST_FIELDS；传 rename 则按传入映射（未命中保留原 f 键）。
    """
    if not fields:
        fields = "f2,f3,f4,f5,f6,f8,f9,f12,f13,f14,f20,f104,f105,f106"
    j = client.get_json(CLIST_URL,
                        params={"pn": page, "pz": page_size, "po": po, "np": 1, "fltt": 2,
                                "invt": 2, "fid": fid, "fs": fs, "fields": fields},
                        referer=_REFERER)
    rows = (j.get("data") or {}).get("diff") or []
    mapping = rename if rename is not None else _CLIST_FIELDS
    return [_rename_fields(r, mapping) for r in rows]


_CLIST_FIELDS = {"f2": "price", "f3": "pct_change", "f4": "change", "f5": "volume",
                 "f6": "amount", "f8": "turnover_rate", "f9": "pe_dynamic",
                 "f12": "code", "f13": "market", "f14": "name", "f20": "total_mv",
                 "f104": "up_count", "f105": "down_count", "f106": "flat_count"}


def _rename_fields(r: dict, mapping: dict) -> dict:
    out = {}
    for f, v in r.items():
        out[mapping.get(f, f)] = v
    return out


def _rename_clist(r: dict) -> dict:
    return _rename_fields(r, _CLIST_FIELDS)


# ---- 资金流向（push2 clist / ulist）----
# 字段语义权威来源：https://data.eastmoney.com/newstatic/js/zjlx/detail.js 的 mapping
#   f62/f267/f164/f174 = 主力净额（今日/3日/5日/10日）
#   f184/f268/f165/f175 = 主力净占比；f66..= 超大单；f72..= 大单；f78..= 中单；f84..= 小单
FLOW_RENAME = {
    "f12": "code", "f13": "market", "f14": "name", "f2": "price",
    "f3": "pct_change", "f127": "pct_change", "f109": "pct_change", "f160": "pct_change",
    "f124": "update_time",
    "f62": "main_net", "f184": "main_net_pct",
    "f66": "super_net", "f69": "super_net_pct",
    "f72": "large_net", "f75": "large_net_pct",
    "f78": "mid_net", "f81": "mid_net_pct",
    "f84": "small_net", "f87": "small_net_pct",
    "f267": "main_net", "f268": "main_net_pct",
    "f269": "super_net", "f270": "super_net_pct",
    "f271": "large_net", "f272": "large_net_pct",
    "f273": "mid_net", "f274": "mid_net_pct",
    "f275": "small_net", "f276": "small_net_pct",
    "f164": "main_net", "f165": "main_net_pct",
    "f166": "super_net", "f167": "super_net_pct",
    "f168": "large_net", "f169": "large_net_pct",
    "f170": "mid_net", "f171": "mid_net_pct",
    "f172": "small_net", "f173": "small_net_pct",
    "f174": "main_net", "f175": "main_net_pct",
    "f176": "super_net", "f177": "super_net_pct",
    "f178": "large_net", "f179": "large_net_pct",
    "f180": "mid_net", "f181": "mid_net_pct",
    "f182": "small_net", "f183": "small_net_pct",
    "f204": "top_stock_name", "f205": "top_stock_code",
    "f257": "top_stock_name", "f258": "top_stock_code",
    "f260": "top_stock_name", "f261": "top_stock_code",
}

# stat 口径 → (fields, 排序字段)。取自 detail.js pageopt.statvalues。
FLOW_STAT = {
    "today": ("f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13", "f62"),
    "3d": ("f12,f14,f2,f127,f267,f268,f269,f270,f271,f272,f273,f274,f275,f276,f257,f258,f124,f1,f13", "f267"),
    "5d": ("f12,f14,f2,f109,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f257,f258,f124,f1,f13", "f164"),
    "10d": ("f12,f14,f2,f160,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f260,f261,f124,f1,f13", "f174"),
}

# 市场口径 → fs。取自 detail.js pageopt.mktvalues。
FLOW_FS = {
    "all": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2",
    "hsa": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2",
    "sha": "m:1+t:2+f:!2,m:1+t:23+f:!2",
    "kcb": "m:1+t:23+f:!2",
    "sza": "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2",
    "cyb": "m:0+t:80+f:!2",
    "zxb": "m:0+t:13+f:!2",
    "hb": "m:1+t:3+f:!2",
    "sb": "m:0+t:7+f:!2",
    "bja": "m:0+t:81+s:262144+f:!2",
}

# 板块口径 → fs。取自 bkzj/list.js bkvalues（注意行业为 m:90+s:4）。
FLOW_FS_BOARD = {"industry": "m:90+s:4", "concept": "m:90+t:3", "region": "m:90+t:1"}


def flow_rank(client, fs: str, stat: str = "today", fid: str = "",
              page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """资金流向排行（个股/板块通用）：按 stat 口径取字段，按主力净额降序。"""
    fields, default_fid = FLOW_STAT.get(stat, FLOW_STAT["today"])
    return clist(client, fs=fs, fields=fields, rename=FLOW_RENAME,
                 fid=fid or default_fid, po=1, page_size=page_size, page=page)


# 大盘/指数资金流：ulist.np/get 字段集（取自 dapan.js）
# 注：实测 f278..f282 与 f164..f172 取值完全相同（同为 5 日，接口别名），故不重复请求。
_MKT_FLOW_FIELDS = ("f12,f13,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f64,f65,"
                    "f70,f71,f76,f77,f82,f83,f164,f166,f168,f170,f172,"
                    "f252,f253,f254,f255,f256,f124,f6")
_MKT_FLOW_RENAME = {
    "f12": "code", "f13": "market", "f14": "name", "f124": "update_time", "f6": "amount",
    "f62": "main_net", "f184": "main_net_pct",
    "f66": "super_net", "f69": "super_net_pct",
    "f72": "large_net", "f75": "large_net_pct",
    "f78": "mid_net", "f81": "mid_net_pct",
    "f84": "small_net", "f87": "small_net_pct",
    "f64": "super_in", "f65": "super_out", "f70": "large_in", "f71": "large_out",
    "f76": "mid_in", "f77": "mid_out", "f82": "small_in", "f83": "small_out",
    "f164": "main_net_5d", "f166": "super_net_5d", "f168": "large_net_5d",
    "f170": "mid_net_5d", "f172": "small_net_5d",
    "f252": "main_net_10d", "f253": "super_net_10d", "f254": "large_net_10d",
    "f255": "mid_net_10d", "f256": "small_net_10d",
}

# 指数 secid：沪深两市 / 沪市 / 深市 / 创业板 / 沪B / 深B / 科创板
INDEX_SECIDS = {
    "hs2": "1.000001,0.399001", "sh": "1.000001", "sz": "0.399001",
    "cyb": "0.399006", "shb": "1.000003", "szb": "0.399003", "kcb": "1.000688",
    "hs300": "1.000300",
}


def market_flow(client, secids: str = "1.000001,0.399001", **kw) -> list[dict]:
    """大盘/指数资金流（实时）：返回各指数的主力/超大/大/中/小 净额与占比 + 3/5/10日。"""
    j = client.get_json(ULIST_URL,
                        params={"fltt": 2, "secids": secids, "fields": _MKT_FLOW_FIELDS,
                                "ut": "b2884a393a59ad64002292a3e90d46a5"},
                        referer="https://data.eastmoney.com/zjlx/dpzjlx.html")
    rows = (j.get("data") or {}).get("diff") or []
    return [_rename_fields(r, _MKT_FLOW_RENAME) for r in rows]


def ulist(client, secids: str, fields: str = "f12,f14", **kw) -> list[dict]:
    j = client.get_json(ULIST_URL,
                        params={"secids": secids, "fields": fields, "fltt": 2},
                        referer="https://quote.eastmoney.com/")
    return (j.get("data") or {}).get("diff") or []


def stock_flow_rank(client, market: str = "all", stat: str = "today",
                    page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """个股资金流向排行：market ∈ all/hsa/sha/kcb/sza/cyb/zxb/hb/sb/bja。"""
    fs = FLOW_FS.get(market, FLOW_FS["all"])
    return flow_rank(client, fs=fs, stat=stat, page_size=page_size, page=page)


def board_flow_rank(client, board: str = "industry", stat: str = "today",
                    page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """板块资金流向排行：board ∈ industry/concept/region。"""
    fs = FLOW_FS_BOARD.get(board, FLOW_FS_BOARD["industry"])
    return flow_rank(client, fs=fs, stat=stat, page_size=page_size, page=page)


def board_stock_flow(client, board_code: str, stat: str = "today",
                     page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """板块内个股资金流：board_code 形如 BK0475。"""
    return flow_rank(client, fs=f"b:{board_code}", stat=stat,
                     page_size=page_size, page=page)


def index_flow(client, index: str = "hs2", **kw) -> list[dict]:
    """大盘/指数资金流：index ∈ hs2/sh/sz/cyb/shb/szb/kcb。"""
    return market_flow(client, secids=INDEX_SECIDS.get(index, INDEX_SECIDS["hs2"]))


def index_flow_kline(client, index: str = "sh", lmt: int = 20, **kw) -> list[dict]:
    """单指数资金流历史（日序列）。"""
    from em.providers.fflow import moneyflow
    secid = INDEX_SECIDS.get(index, INDEX_SECIDS["sh"]).split(",")[0]
    return moneyflow(client, secid=secid, lmt=lmt)


# =====================================================================
# P2-c 行情中心长尾：市场清单 / 盘口异动 / 沪深港通 / 港美股快照 / 期货期权
# fs 口径全部取自 quote.eastmoney.com 站点公开配置（sidemenu_new.json 与各页面 JS），非猜测。
# =====================================================================

# 名称 → clist fs。口径逐条取自 quote.eastmoney.com 站点配置
# `center/static/build/index.js` 的 `hashtable`（154 条）与 `hashqhtable`，非猜测；每条均已实测非空。
NAMED_FS = {
    # ---- A 类 · A股清单与比价 ----
    "stock_list": "m:0+t:6+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:81+s:262144+f:!2",
    "stock_list_sh": "m:1+t:2+f:!2,m:1+t:23+f:!2",
    "stock_list_sh_zcz": "m:1+t:2+s:131072+f:!2,m:1+t:23+s:131072+f:!2",
    "stock_list_sh_hzz": "m:1+t:2+s:524288+f:!2,m:1+t:23+s:524288+f:!2",
    "stock_list_sz": "m:0+t:6+f:!2,m:0+t:80+f:!2",
    "stock_list_sz_zcz": "m:0+t:6+s:131072+f:!2,m:0+t:80+s:131072+f:!2",
    "stock_list_sz_hzz": "m:0+t:6+s:524288+f:!2,m:0+t:80+s:524288+f:!2",
    "stock_list_bj": "m:0+t:81+s:262144+f:!2",
    "stock_list_gem": "m:0+t:80+f:!2",
    "stock_list_gem_zcz": "m:0+t:80+s:131072+f:!2",
    "stock_list_gem_hzz": "m:0+t:80+s:!131072+f:!2",
    "stock_list_kcb": "m:1+t:23+f:!2",
    "stock_list_b": "m:0+t:7+f:!2,m:1+t:3+f:!2",
    "new_stock_list": "m:0+f:8,m:1+f:8",
    "st_stock_list": "m:0+f:4,m:1+f:4,i:0.920023,i:0.920090,i:0.920575",
    "st_stock_list_sh": "m:1+f:4",
    "st_stock_list_sz": "m:0+f:4",
    "st_stock_list_bj": "i:0.920023,i:0.920090,i:0.920575",
    "st_stock_list_kcb": "m:1+t:23+f:4",
    "st_stock_list_gem": "m:0+t:80+f:4",
    "delisted_stock_list": "m:0+s:3",
    "neeq_stock_list": "m:0+t:81+s:!2052",
    "neeq_innovate": "m:0+s:512",
    "neeq_basic": "m:0+s:256",
    "neeq_marketmaking": "m:0+s:128",
    "neeq_bidding": "m:0+s:32",
    "hsgt_stock_list_sh": "b:BK0707",
    "hsgt_stock_list_sz": "b:BK0804",
    "ah_comparison": "b:MK0101",
    "ab_comparison": "m:1+b:BK0498,m:0+b:BK0498",
    "ab_comparison_sh": "m:1+b:BK0498",
    "ab_comparison_sz": "m:0+b:BK0498",
    # ---- 指数 ----
    "index_list_sh": "m:1+t:1",
    "index_list_sz": "m:0+t:5",
    "index_zzzs": "m:2",
    "index_components": "m:1+s:3",
    # ---- B 类 · 板块 ----
    "region_board": "m:90+t:1+f:!50",
    "industry_board_1": "m:90+s:2+f:!50",
    "industry_board_2": "m:90+s:4+f:!50",
    "industry_board_3": "m:90+s:8+f:!50",
    # ---- C 类 · 沪深港通 ----
    "hsgt_etf_sh": "b:MK0839",
    "hsgt_etf_sz": "b:MK0840",
    "hk_hsgt_etf_sh": "b:MK0838",
    "hk_hsgt_etf_sz": "b:MK0837",
    "hk_hsgt_etf_all": "b:MK0838+b:MK0837",
    "hk_hsgt_list_sh": "b:MK0144",
    "hk_hsgt_list_sz": "b:MK0146",
    "hk_hsgt_list_all": "b:MK0146,b:MK0144",
    # ---- D 类 · 港股市场 ----
    "hk_stock_list": "m:116+t:3,m:116+t:4,m:116+t:1,m:116+t:2",
    "hk_main_board": "m:116+t:3",
    "hk_gem": "m:116+t:4",
    "hk_known_list": "b:MK0106",
    "hk_blue_chip_list": "b:MK0105",
    "hk_red_chip_list": "b:MK0102",
    "hk_red_chip_components": "b:MK0111",
    "hk_soe_list": "b:MK0103",
    "hk_soe_components": "b:MK0112",
    "hk_rmb_stock_list": "m:116+s:64",
    "hk_hsics_large": "b:MK0141",
    "hk_hsics_mid": "b:MK0142",
    "hk_adr_list": "m:116+s:1",
    "hk_index_list": "m:124,m:125,m:305",
    "hk_warrant_list": "m:116+t:6",
    "hk_cbbc_list": "m:116+t:5",
    # ---- E 类 · 美股 / 英股 / 瑞士 ----
    "us_stock_list": "m:105,m:106,m:107",
    "us_known_list": "b:MK0001",
    "us_technology": "b:MK0216",
    "us_financial": "b:MK0217",
    "us_medicine_food": "b:MK0218",
    "us_automotive_energy": "b:MK0219",
    "us_media": "b:MK0220",
    "us_manufacture_retail": "b:MK0221",
    "us_china_list": "b:MK0201",
    "us_china_net_list": "b:MK0202",
    "us_index_list": "i:100.NDX,i:100.DJIA,i:100.SPX",
    "us_otc_list": "m:153",
    "uk_list": "m:155+t:1,m:155+t:2,m:155+t:3,m:156+t:1,m:156+t:2,m:156+t:5,"
               "m:156+t:6,m:156+t:7,m:156+t:8,b:MK0794,m:341",
    "ch_gdr_list": "m:252+t:1",
    # ---- F 类 · 基金 / REITs ----
    "etf_list": "b:MK0021,b:MK0022,b:MK0023,b:MK0024,b:MK0827",
    "lof_list": "b:MK0404,b:MK0405,b:MK0406,b:MK0407",
    "reits_list": "m:1+t:9+e:97,m:0+t:10+e:97",
    "reits_list_sh": "m:1+t:9+e:97",
    "reits_list_sz": "m:0+t:10+e:97",
    # ---- G 类 · 债券 ----
    "bond_index_list": "i:1.000012,i:1.000013,i:1.000022,i:1.000061,i:0.395021,"
                       "i:0.395022,i:0.395031,i:0.395032,i:0.399481",
    "bond_spot_list_sh": "m:1+t:4",
    "bond_spot_list_sz": "m:0+t:8",
    "bond_spot_list_bj": "m:0+t:35",
    "bond_sh_treasury": "m:1+b:MK0351",
    "bond_sh_enterprise": "m:1+b:MK0353",
    "bond_sh_convertible": "m:1+b:MK0354",
    "bond_sz_treasury": "m:0+b:MK0351",
    "bond_sz_enterprise": "m:0+b:MK0353",
    "bond_sz_convertible": "m:0+b:MK0354",
    "bond_bj_enterprise": "m:0+t:35+e:10",
    "repo_sh": "m:1+b:MK0356",
    "repo_sz": "m:0+b:MK0356",
    "convertible_bond_comparison": "b:MK0354",
    # ---- H 类 · 外汇（6 家银行牌价分列）----
    "forex_list": "m:119,m:120,m:133",
    "forex_basic": "b:MK0300",
    "forex_cross": "b:MK0301",
    "forex_cny": "m:120+t:!2,m:133",
    "forex_cnyc": "b:MK0002",
    "forex_cnh": "m:133",
    "forex_bank_icbc": "m:162+s:1",
    "forex_bank_abc": "m:162+s:2",
    "forex_bank_boc": "m:162+s:4",
    "forex_bank_ccb": "m:162+s:8",
    "forex_bank_bcm": "m:162+s:16",
    "forex_bank_cmb": "m:162+s:32",
    # ---- I 类 · 黄金 ----
    "gold_sh_spot": "m:118",
    "gold_sh_futures": "m:113+t:5",
    "gold_global_spot": "m:122,m:123",
    "gold_global_futures": "i:111.JAGC,i:101.QI00Y,i:111.JPAC,i:101.HG00Y,i:111.JAUC,"
                           "i:111.JPLC,i:102.PL00Y,i:101.QO00Y,i:101.MGC00Y,i:101.GC00Y,"
                           "i:101.SI00Y,i:102.PA00Y",
    # ---- J 类 · 期货（各交易所品种行情）----
    "futures_shfe": "m:113",
    "futures_ine": "m:142",
    "futures_dce": "m:114",
    "futures_czce": "m:115",
    "futures_gfex": "m:225",
    "futures_cffex": "m:220",
    # ---- K 类 · 期权 ----
    "option_list_sse": "m:10",
    "option_list_szse": "m:12",
    "option_list_all": "m:10,m:140,m:141,m:151,m:163,m:226",
    "option_call_sse": "m:10+t:173",
    "option_put_sse": "m:10+t:174",
    "option_call_szse": "m:12+t:178",
    "option_put_szse": "m:12+t:179",
    "option_cffex_all": "m:221",
    "option_cffex_hs300": "m:221+t:1",
    "option_cffex_zz1000": "m:221+t:2",
}

# 期货合约子列表：market → 交易所市场码
FUTURES_MARKET = {"shfe": 113, "ine": 142, "dce": 114, "czce": 115, "gfex": 225, "cffex": 220}
# 商品/股指期权子列表：market → 期权市场码
OPTION_MARKET = {"shfe": 151, "dce": 140, "czce": 141, "ine": 163, "gfex": 226, "cffex": 221}
# 期权 T 型报价标的：underlying → (clist fs 前缀, 认购 t 码, 认沽 t 码)
OPTION_UNDERLYING = {
    "510050": ("m:10+c:510050", 173, 174), "510300": ("m:10+c:510300", 173, 174),
    "510500": ("m:10+c:510500", 173, 174), "588000": ("m:10+c:588000", 173, 174),
    "588080": ("m:10+c:588080", 173, 174),
    "159919": ("m:12+c:159919", 178, 179), "159922": ("m:12+c:159922", 178, 179),
    "159915": ("m:12+c:159915", 178, 179),
}
# 未走 clist 的清单（站点用独立接口 / 无公开接口），已实测 clist 返回空或不支持
NAMED_FS_UNAVAILABLE = {
    "fund_close_end": "e:19（封闭基金，clist 无数据，站点走独立接口）",
    "futures_hkex_index": "HKINDEXF（港交所指数期货，clist 不支持）",
    "futures_hkex_stock": "HKSTOCKF（港交所股票期货，clist 不支持）",
    "futures_hkex_fx": "HKCNYF（港交所人民币期货，clist 不支持）",
    "futures_hkex_metal": "HKMETALFS（港交所金属期货，clist 不支持）",
    "futures_global": "COMEX/NYMEX/LME/…（国际期货，站点走 global 专用接口）",
}


def listed(client, name: str, page_size: int = 20, page: int = 1, fid: str = "f3",
           po: int = 1, fields: str = "", **kw) -> list[dict]:
    """按名称取东财行情中心各「市场/标签页」清单（fs 口径见 NAMED_FS）。"""
    fs = NAMED_FS.get(name)
    if not fs:
        raise ValueError(f"未知清单：{name}")
    return clist(client, fs=fs, fields=fields, fid=fid, po=po, page_size=page_size, page=page)


def futures_contracts(client, market: str, product: int = 1, page_size: int = 20,
                      page: int = 1, **kw) -> list[dict]:
    """期货品种合约列表：market ∈ shfe/ine/dce/czce/gfex/cffex，product 为品种序号。"""
    m = FUTURES_MARKET.get(str(market))
    if m is None:
        raise ValueError(f"未知期货市场：{market}")
    return clist(client, fs=f"m:{m}+t:{int(product)}", page_size=page_size, page=page)


def option_contracts(client, market: str, product: int = 1, page_size: int = 20,
                     page: int = 1, **kw) -> list[dict]:
    """商品期权合约列表：market ∈ shfe/dce/czce/ine/gfex，product 为品种序号。"""
    m = OPTION_MARKET.get(str(market))
    if m is None:
        raise ValueError(f"未知期权市场：{market}")
    return clist(client, fs=f"m:{m}+t:{int(product)}", page_size=page_size, page=page)


def option_tquote(client, underlying: str, kind: str = "all", page_size: int = 50,
                  page: int = 1, **kw) -> list[dict]:
    """期权 T 型报价：underlying 为标的代码（如 510050 / 159919），kind ∈ all/call/put。"""
    key = str(underlying).strip()
    tup = OPTION_UNDERLYING.get(key) or OPTION_UNDERLYING.get(key.lstrip("0"))
    if not tup:
        raise ValueError(f"未知期权标的：{underlying}")
    base, t_call, t_put = tup
    fs = base if kind not in ("call", "put") else f"{base}+t:{t_call if kind == 'call' else t_put}"
    return clist(client, fs=fs, page_size=page_size, page=page)


PKYD_URL = "https://push2.eastmoney.com/api/qt/pkyd/get"
_PKYD_UT = "fa5fd1943c7b386f172d6893dbfba10b"


def pkyd(client, kind: str = "", page_size: int = 20, page: int = 1, **kw) -> list[dict]:
    """盘口异动明细（时间/代码/市场/名称）；kind 为异动类型码（缺省=全部/默认类）。"""
    params = {"ut": _PKYD_UT, "np": 1, "fltt": 2, "invt": 2,
              "fields": "f1,f2,f3,f4,f12,f13,f14,f15,f16", "pn": page, "pz": page_size}
    if kind not in ("", None):
        params["type"] = kind
    j = client.get_json(PKYD_URL, params=params, referer=_REFERER)
    rows = (j.get("data") or {}).get("pkyd") or []
    out = []
    for s in rows:
        p = str(s).split(",")
        if len(p) >= 4:
            out.append({"time": p[0], "code": p[1], "market": p[2], "name": p[3]})
    return out


KAMT_URL = "https://push2.eastmoney.com/api/qt/kamt/get"
KAMT_KLINE_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get"
_KAMT_UT = "b2884a393a59ad64002292a3e90d46a5"
_KAMT_LABEL = {"hk2sh": "沪股通(北向)", "hk2sz": "深股通(北向)", "s2n": "北向合计",
               "sh2hk": "港股通(沪)", "sz2hk": "港股通(深)", "n2s": "南向合计"}


def kamt(client, **kw) -> list[dict]:
    """沪深港通实时额度与净流入（分通道）。"""
    j = client.get_json(KAMT_URL, params={"fields1": "f1,f2,f3,f4",
                                          "fields2": "f51,f52,f53,f54,f55,f56", "ut": _KAMT_UT},
                        referer=_REFERER)
    d = j.get("data") or {}
    out = []
    for k, v in d.items():
        if isinstance(v, dict):
            out.append({"channel": k, "channel_name": _KAMT_LABEL.get(k, k), "status": v.get("status"),
                        "net_inflow": _num(v.get("dayNetAmtIn")), "remain": _num(v.get("dayAmtRemain")),
                        "threshold": _num(v.get("dayAmtThreshold")), "date": v.get("date")})
    return out


def kamt_kline(client, lmt: int = 20, **kw) -> list[dict]:
    """沪深港通资金流历史序列（分通道）。"""
    j = client.get_json(KAMT_KLINE_URL, params={"fields1": "f1,f3,f5", "fields2": "f51,f52,f53,f54",
                                                "ut": _KAMT_UT, "klt": 101, "lmt": lmt}, referer=_REFERER)
    d = j.get("data") or {}
    out = []
    for k, arr in d.items():
        for line in (arr or []):
            p = str(line).split(",")
            if len(p) >= 4:
                out.append({"channel": k, "channel_name": _KAMT_LABEL.get(k, k), "date": p[0],
                            "net_inflow": _num(p[1]), "threshold": _num(p[2]), "remain": _num(p[3])})
    return out


def snapshot_by_secid(client, secid: str, **kw) -> dict[str, Any]:
    """按 secid（如 116.00700 / 105.AAPL）取快照，供港/美/国际指数用。"""
    j = client.get_json(SNAPSHOT_URL, params={"secid": secid, "fields": ",".join(_SNAP_FIELDS),
                                              "fltt": 2, "invt": 2}, referer=_REFERER)
    d = j.get("data") or {}
    out = {"secid": secid}
    for f, semantic in _SNAP_FIELDS.items():
        if f in d:
            out[semantic] = d[f]
    return out


def kline_by_secid(client, secid: str, klt: int = 101, fqt: int = 0, lmt: int = 120,
                   end: str = "", **kw) -> list[dict[str, Any]]:
    """按 secid 取 K 线（港/美/外汇等）。"""
    params = {"secid": secid, "klt": klt, "fqt": fqt,
              "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
              "lmt": lmt, "end": (end or "20500101")}
    j = client.get_json(KLINE_URL, params=params, referer=_REFERER)
    data = j.get("data") or {}
    out = []
    for line in (data.get("klines") or []):
        p = line.split(",")
        if len(p) < 11:
            continue
        out.append({"date": p[0], "open": _num(p[1]), "close": _num(p[2]), "high": _num(p[3]),
                    "low": _num(p[4]), "volume": _num(p[5]), "amount": _num(p[6]),
                    "amplitude": _num(p[7]), "pct_change": _num(p[8]), "change": _num(p[9]),
                    "turnover_rate": _num(p[10])})
    return out


def index_snapshot(client, index: str = "sh", **kw) -> dict[str, Any]:
    """市场总貌指数快照：index ∈ hs2/sh/sz/cyb/shb/szb/kcb/hs300。"""
    secid = INDEX_SECIDS.get(index, INDEX_SECIDS["sh"]).split(",")[0]
    return snapshot_by_secid(client, secid)


_BREADTH_KEYS = ("sh", "sz", "cyb", "kcb", "hs300")


def market_breadth(client, index: str = "sh", **kw) -> Any:
    """市场总貌涨跌家数：index 为空/all 返回主要指数列表，否则返回该指数单条。

    上涨/下跌/平盘家数由 push2 ulist.np 的 f104/f105/f106 提供（stock/get 无此字段）。
    """
    if str(index) in ("", "all"):
        secids = ",".join(dict.fromkeys(INDEX_SECIDS[k] for k in _BREADTH_KEYS))
        want_all = True
    else:
        secids = INDEX_SECIDS.get(str(index), INDEX_SECIDS["sh"])
        want_all = False
    j = client.get_json(ULIST_URL,
                        params={"secids": secids, "fltt": 2, "invt": 2,
                                "fields": "f1,f2,f3,f4,f12,f13,f14,f104,f105,f106",
                                "ut": "fa5fd1943c7b386f172d6893dbfba10b"},
                        referer=_REFERER)
    diff = (j.get("data") or {}).get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    out = [{"secid": f"{r.get('f13')}.{r.get('f12')}", "code": r.get("f12"),
            "name": r.get("f14"), "price": _num(r.get("f2")),
            "pct_change": _num(r.get("f3")), "change": _num(r.get("f4")),
            "up_count": _num(r.get("f104")), "down_count": _num(r.get("f105")),
            "flat_count": _num(r.get("f106"))} for r in diff]
    if want_all:
        return out
    return out[0] if out else {}


def _num(v: Any) -> float | None:
    try:
        if v in ("", "-", None):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_secids(codes: list[str]) -> str:
    return ",".join(_secid(c) for c in codes)


ENDPOINTS = {
    "quote.snapshot": snapshot,
    "quote.kline": kline,
    "quote.trends": trends,
    "quote.orderbook": orderbook,
    "quote.clist": clist,
    "quote.ulist": ulist,
    "flow.stock_rank": stock_flow_rank,
    "flow.board_rank": board_flow_rank,
    "flow.board_stock": board_stock_flow,
    "flow.index": index_flow,
    "flow.index_kline": index_flow_kline,
    # P2-c 长尾
    "quote.listed": listed,
    "quote.futures_contracts": futures_contracts,
    "quote.option_contracts": option_contracts,
    "quote.option_tquote": option_tquote,
    "quote.pkyd": pkyd,
    "quote.kamt": kamt,
    "quote.kamt_kline": kamt_kline,
    "quote.snapshot_secid": snapshot_by_secid,
    "quote.kline_secid": kline_by_secid,
    "quote.index_snapshot": index_snapshot,
    "quote.market_breadth": market_breadth,
}