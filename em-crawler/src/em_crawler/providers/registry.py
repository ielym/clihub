"""汇总所有 provider endpoint 到单一注册表。"""
from __future__ import annotations

from em_crawler.providers.quote import ENDPOINTS as _QUOTE
from em_crawler.providers.datacenter import ENDPOINTS as _DC
from em_crawler.providers.fflow import ENDPOINTS as _FFLOW
from em_crawler.providers.news import ENDPOINTS as _NEWS
from em_crawler.providers.fund import ENDPOINTS as _FUND
from em_crawler.providers.f10 import ENDPOINTS as _F10
from em_crawler.providers.guba import ENDPOINTS as _GUBA
from em_crawler.providers.pool import ENDPOINTS as _POOL
from em_crawler.providers.macro import ENDPOINTS as _MACRO
from em_crawler.providers.tools import ENDPOINTS as _TOOLS
from em_crawler.providers.cross import ENDPOINTS as _CROSS
from em_crawler.providers.event import ENDPOINTS as _EVENT
from em_crawler.providers.extended import ENDPOINTS as _EXTENDED

ENDPOINTS: dict = {}
for m in (_QUOTE, _DC, _FFLOW, _NEWS, _FUND, _F10, _GUBA, _POOL, _MACRO, _TOOLS, _CROSS, _EVENT, _EXTENDED):
    ENDPOINTS.update(m)


def register(mapping: dict) -> None:
    ENDPOINTS.update(mapping)