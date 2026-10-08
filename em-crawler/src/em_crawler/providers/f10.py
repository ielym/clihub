"""F10 PageAjax Provider：新版 JSON 模块解析（A股）+ 港股概况。

东财 F10（PC_HSF10）模块接口返回的是 **JSON**（旧实现按 HTML <table> 解析，
故 rows 恒为 0）。此处按真实 JSON 结构解析，并把每个顶层键归一化为行列表，
metric 通过 field 指定所需子表键（如 ssbk / jgcc / dstx）。
"""
from __future__ import annotations

import json

from em_crawler.providers import _market

F10_PAGEAJAX = "https://emweb.securities.eastmoney.com/PC_HSF10/"
HKF10_PAGEAJAX = "https://emweb.securities.eastmoney.com/PC_HKF10/"
F10_REFERER = "https://emweb.securities.eastmoney.com/"
# 港股/美股 F10 大事提醒（/securities/api/data/get，参数为 type + params）
DC_SEC_GET = "https://datacenter.eastmoney.com/securities/api/data/get"

# metric 里的模块别名 → 东财真实模块名（无效模块名已剔除）
MODULES = {
    "f10_survey": "CompanySurvey",            # 基本资料 jbzl / 发行相关 fxxg
    "f10_concept": "CoreConception",          # 核心题材 ssbk / hxtc
    "f10_holding": "ShareholderResearch",     # 股东研究 gdrs/sdgd/ltgf/jgcc/jjcg...
    "f10_structure": "CapitalStockStructure",  # 股本结构 xsjj/gbjg/lngbbd/gbgc
    "f10_event": "CompanyBigNews",            # 公司大事 dstx + 各事件子表
    "f10_management": "CompanyManagement",    # 公司高管 gglb / 持股变动 cgbd
    "f10_capital_op": "CapitalOperation",     # 资本运作 mjzjly / xmjd
    "f10_bonus": "BonusFinancing",            # 分红融资 fhyx/lnfhrz/zfmx/pgmx
    "f10_industry": "IndustryAnalysis",       # 行业分析 czxbj/gzbj/dbfxbj/scbx/gsgm*
    "f10_business": "BusinessAnalysis",       # 经营分析 zyfw/zygcfx/jyps
    "f10_forecast": "ProfitForecast",         # 盈利预测 pjtj/jgyc/yctj_list/ycmx
    "f10_relation": "StockRelationship",      # 关联个股 hy / ggpm
    "f10_news": "NewsBulletin",               # 新闻公告 gszx / gsgg
    "f10_required": "OperationsRequired",     # 操盘必读聚合
}


def f10_module(client, code: str, module: str, **kw) -> dict:
    """抓取 F10 某模块 PageAjax，返回 {子表键: 行列表} 的归一化结构。"""
    page = MODULES.get(module, module)
    jscode = f"{_market(code)}{code}"
    data = client.get_json(f"{F10_PAGEAJAX}{page}/PageAjax",
                           params={"code": jscode}, referer=F10_REFERER)
    return normalize(data)


def f10_foreign(client, secucode: str, **kw) -> dict:
    """港股（PC_HKF10）公司概况。美股 F10 走独立 SPA 接口，暂不支持。"""
    code, _, mkt = str(secucode).partition(".")
    if mkt.upper() != "HK":
        return {}
    text = client.get_text(f"{HKF10_PAGEAJAX}CompanyProfile/PageAjax",
                           params={"code": code}, referer=F10_REFERER)
    data = _loads(text)
    out: dict = {}
    for key in ("zqzl", "gszl"):
        sec = data.get(key)
        if isinstance(sec, dict):
            out.update(sec)
    return out


def f10_detail(client, secucode: str, kind: str = "index", **kw) -> list[dict]:
    """港股/美股 F10 大事提醒。secucode 如 00700.HK / AAPL.O；kind=index|detail。

    该接口响应体为嵌套 list（[[未来事件], [历史事件]]），此处展平为行列表。
    """
    code = str(secucode).strip()
    mkt = code.partition(".")[2].upper()
    if mkt == "HK":
        prefix = "RPT_F10_HK"
    elif mkt in ("O", "N", "A", "US"):
        prefix = "RPT_F10_US"
    else:
        return []
    report = f"{prefix}_{'DETAIL' if kind == 'detail' else 'INDEX'}"
    j = client.get_json(DC_SEC_GET, params={"type": report, "params": code, "p": 1,
                                            "source": "F10", "client": "PC"},
                        referer=F10_REFERER)
    data = j.get("data") if isinstance(j, dict) else None
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for it in data:
        if isinstance(it, list):
            out.extend(x for x in it if isinstance(x, dict))
        elif isinstance(it, dict):
            out.append(it)
    return out


def normalize(data) -> dict:
    if not isinstance(data, dict):
        return {}
    return {k: _rows(v) for k, v in data.items()}


def _rows(v):
    """把单键值归一化为行列表：展开 {data:...}/{items:...} 与 [[...]] 嵌套。"""
    if isinstance(v, list):
        out = []
        for it in v:
            if isinstance(it, list):
                out.extend(x for x in it if isinstance(x, dict))
            elif isinstance(it, dict):
                out.append(it)
        return out
    if isinstance(v, dict):
        if isinstance(v.get("data"), (list, dict)):
            return _rows(v["data"])
        if isinstance(v.get("items"), list):
            return _rows(v["items"])
    return v


def _loads(text) -> dict:
    """宽松 JSON 解析：容忍 BOM 前缀与非 JSON 响应。"""
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return {}
    try:
        return json.loads(text.lstrip("\ufeff").strip())
    except (ValueError, TypeError):
        return {}


ENDPOINTS = {
    "f10.module": f10_module,
    "f10.foreign": f10_foreign,
    "f10.detail": f10_detail,
}