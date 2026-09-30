"""数据源注册与查找。"""
from __future__ import annotations

from typing import Optional

from .base import Source
from .sources import ALL_SOURCES

_BY_COMMAND = {s.command: s for s in ALL_SOURCES}
_BY_NAME = {s.name: s for s in ALL_SOURCES}


def all_sources() -> list[Source]:
    return list(ALL_SOURCES)


def by_command(command: str) -> Optional[Source]:
    return _BY_COMMAND.get(command)


def by_name(name: str) -> Optional[Source]:
    return _BY_NAME.get(name)