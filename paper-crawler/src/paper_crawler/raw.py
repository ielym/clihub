"""原始记录：数据源抓取的统一输出单元。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawRecord:
    """一条尚未加工的原始记录。

    字段:
        source: 数据源标识
        source_id: 数据源内的记录 ID
        content_type: 原始内容类型（json / atom_xml / xml / html）
        fetched_at: 抓取时间（UTC）
        data: 原始内容（dict / str）
        metadata: 抓取上下文（查询式、会议、榜单名次等）
    """

    source: str
    source_id: str
    content_type: str
    fetched_at: datetime
    data: Any
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "content_type": self.content_type,
            "fetched_at": self.fetched_at.isoformat(),
            "metadata": self.metadata,
            "data": self.data,
        }