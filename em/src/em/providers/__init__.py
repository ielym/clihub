"""provider 注册表：name -> callable(client, **args) -> normalized dict/list。

metric 目录引用这些 endpoint，查询引擎按 (endpoint, args) 分组合并请求。
"""
from __future__ import annotations


def _secid(code: str, market: str = "") -> str:
    """股票代码 → 东财 secid（市场.代码），A 股按代码段推断市场。"""
    code = str(code).strip()
    if market:
        m = {"SH": "1", "SZ": "0", "BJ": "0", "sh": "1", "sz": "0", "bj": "0"}.get(market, market)
        return f"{m}.{code}"
    if code.startswith(("6", "9", "5")):
        return f"1.{code}"
    if code.startswith(("4", "8", "92")):
        return f"0.{code}"
    return f"0.{code}"


def _market(code: str) -> str:
    """代码 → 市场简称（SH/SZ/BJ），用于 datacenter SECUCODE 拼接。"""
    code = str(code)
    if code.startswith(("4", "8", "92")):
        return "BJ"
    if code.startswith(("6", "9", "5")):
        return "SH"
    return "SZ"


def _secucode(code: str) -> str:
    return f"{code}.{_market(code)}"