"""数据源基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .context import FetchContext, RateLimitConfig
from .raw import RawRecord


class Source(ABC):
    """单个数据源的抓取器。

    每个数据源只负责一件事：从远端拉取原始记录，产出 RawRecord 流。
    """

    name: str       # 数据源标识
    command: str    # CLI 指令名
    summary: str    # 一句话说明

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig()

    @abstractmethod
    def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        """拉取原始记录。子类实现。"""
        ...