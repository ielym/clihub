"""指标目录：加载 metrics.yaml，提供 metric 定义与查询。

metric 结构（YAML 一条）：
  id, name, aliases, group, kind(scalar|series|table), unit, value_type,
  args(参数表), calibrations(口径), providers(兜底链), equivalence(一致性断言),
  status(ok|offline)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_CATALOG_PATH = Path(__file__).parent / "metrics.yaml"


@dataclass
class ProviderRef:
    """metric 的一个 provider 源：endpoint 名 + 提取字段 + 参数绑定 + 优先级。"""
    endpoint: str
    field: str
    priority: int = 1
    args: dict[str, Any] = field(default_factory=dict)
    row: str = "last"          # 列表结果取值行：last | first | index | all
    note: str = ""


@dataclass
class Metric:
    id: str
    name: str
    group: str
    kind: str                    # scalar | series | table
    value_type: str = "float"
    unit: str = ""
    aliases: list[str] = field(default_factory=list)
    args: dict[str, dict] = field(default_factory=dict)
    calibrations: dict[str, dict] = field(default_factory=dict)
    providers: list[ProviderRef] = field(default_factory=list)
    equivalence: dict = field(default_factory=dict)
    description: str = ""
    status: str = "ok"           # ok | offline（上游已下线，保留定义但不可调用）

    # ---- 便捷查询 ----
    def calibration(self, name: str) -> dict | None:
        return self.calibrations.get(name)

    def primary(self) -> ProviderRef | None:
        return self.providers[0] if self.providers else None

    def fallbacks(self) -> list[ProviderRef]:
        return self.providers[1:]


class Catalog:
    def __init__(self, metrics: dict[str, Metric], groups: dict[str, str]):
        self.metrics = metrics
        self.groups = groups

    def get(self, name: str) -> Metric | None:
        if name in self.metrics:
            return self.metrics[name]
        # 别名匹配
        for m in self.metrics.values():
            if name in m.aliases or name.lower() in [a.lower() for a in m.aliases]:
                return m
        return None

    def by_group(self, group: str) -> list[Metric]:
        return [m for m in self.metrics.values() if m.group == group]

    def all(self) -> list[Metric]:
        return list(self.metrics.values())


def _parse_provider(d: dict) -> ProviderRef:
    return ProviderRef(
        endpoint=d["endpoint"], field=d.get("field", ""),
        priority=int(d.get("priority", 1)),
        args=dict(d.get("args", {}) or {}),
        row=d.get("row", "last"), note=d.get("note", ""),
    )


def load(path: str | Path | None = None) -> Catalog:
    path = Path(path) if path else _CATALOG_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = data.get("groups", {})
    metrics: dict[str, Metric] = {}
    for raw in data.get("metrics", []):
        m = Metric(
            id=raw["id"], name=raw.get("name", raw["id"]),
            group=raw.get("group", ""), kind=raw.get("kind", "scalar"),
            value_type=raw.get("value_type", "float"), unit=raw.get("unit", ""),
            aliases=list(raw.get("aliases", []) or []),
            args=dict(raw.get("args", {}) or {}),
            calibrations=dict(raw.get("calibrations", {}) or {}),
            providers=[_parse_provider(p) for p in raw.get("providers", [])],
            equivalence=dict(raw.get("equivalence", {}) or {}),
            description=raw.get("description", ""),
            status=raw.get("status", "ok"),
        )
        metrics[m.id] = m
    return Catalog(metrics=metrics, groups=groups)