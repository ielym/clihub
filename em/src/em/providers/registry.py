"""汇总所有 provider endpoint 到单一注册表。"""
from __future__ import annotations

from em.providers.quote import ENDPOINTS as _QUOTE
from em.providers.datacenter import ENDPOINTS as _DC
from em.providers.fflow import ENDPOINTS as _FFLOW
from em.providers.news import ENDPOINTS as _NEWS
from em.providers.fund import ENDPOINTS as _FUND
from em.providers.f10 import ENDPOINTS as _F10
from em.providers.guba import ENDPOINTS as _GUBA
from em.providers.pool import ENDPOINTS as _POOL
from em.providers.macro import ENDPOINTS as _MACRO
from em.providers.tools import ENDPOINTS as _TOOLS
from em.providers.cross import ENDPOINTS as _CROSS
from em.providers.event import ENDPOINTS as _EVENT
from em.providers.extended import ENDPOINTS as _EXTENDED

ENDPOINTS: dict = {}
for m in (_QUOTE, _DC, _FFLOW, _NEWS, _FUND, _F10, _GUBA, _POOL, _MACRO, _TOOLS, _CROSS, _EVENT, _EXTENDED):
    ENDPOINTS.update(m)


def register(mapping: dict) -> None:
    ENDPOINTS.update(mapping)