#!/usr/bin/env python3
"""从 metrics.yaml 生成「指标全量参考」Markdown。

用法：
    python3 tools/gen_metrics_reference.py <输出 markdown 路径>

数据源：src/em_crawler/catalog/metrics.yaml（唯一真相源）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from em_crawler.catalog import load  # noqa: E402


def fmt_args(args: dict) -> str:
    if not args:
        return "-"
    parts = []
    for k, v in args.items():
        req = isinstance(v, dict) and v.get("required")
        parts.append(f"{k}*" if req else k)
    return ", ".join(parts)


def fmt_calibrations(cals: dict) -> str:
    if not cals:
        return "-"
    parts = []
    for k, spec in cals.items():
        vals = spec.get("values") or []
        default = spec.get("default")
        v = "|".join(str(x) for x in vals) if vals else "-"
        parts.append(f"{k}={v}（默认 {default}）")
    return "；".join(parts)


def fmt_chain(providers) -> str:
    if not providers:
        return "-"
    parts = []
    for p in sorted(providers, key=lambda x: x.priority):
        a = ",".join(f"{k}={v}" for k, v in (p.args or {}).items())
        field = f".{p.field}" if p.field else ""
        row = f"[{p.row}]" if p.row not in ("last", "") else ""
        seg = f"{p.endpoint}{('(' + a + ')') if a else ''}{field}{row}"
        if p.priority > 1:
            seg += "⤵"
        parts.append(seg)
    return " → ".join(parts)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("metrics.md")
    cat = load()

    lines: list[str] = []
    lines.append("# em-crawler 指标全量参考（%d 个）" % len(cat.metrics))
    lines.append("")
    lines.append("> 本文件由 `clihub/em-crawler/tools/gen_metrics_reference.py` 从 "
                 "`src/em_crawler/catalog/metrics.yaml` 自动生成，请勿手工编辑。")
    lines.append("")
    lines.append("## 阅读说明")
    lines.append("")
    lines.append("| 列 | 含义 |")
    lines.append("| :- | :- |")
    lines.append("| 指标 | 调用时的指标 id：`em-crawler <指标> <参数值>` |")
    lines.append("| kind | `scalar` 单值 / `series` 序列 / `table` 清单 |")
    lines.append("| 参数 | 该指标接受的参数；带 `*` 为必填。除 `code` 外的唯一必填参数可用位置参数传入 |")
    lines.append("| 口径 | 可传 `--<key> <value>`，括号内为默认值 |")
    lines.append("| 数据源链 | 按优先级升序，命中即停；`⤵` 标记兜底源，命中时结果 `fallback=true` |")
    lines.append("")
    lines.append("## 分组索引")
    lines.append("")
    lines.append("| 分组键 | 组名 | 指标数 |")
    lines.append("| :- | :- | :-: |")
    order = list(cat.groups.keys())
    by_group: dict[str, list] = {g: [] for g in order}
    for m in cat.metrics.values():
        by_group.setdefault(m.group, []).append(m)
    for g in order:
        lines.append(f"| `{g}` | {cat.groups[g]} | {len(by_group.get(g, []))} |")
    lines.append(f"| — | **合计** | **{len(cat.metrics)}** |")
    lines.append("")

    for g in order:
        ms = sorted(by_group.get(g, []), key=lambda x: x.id)
        lines.append(f"## {cat.groups[g]} `{g}`（{len(ms)} 个）")
        lines.append("")
        lines.append("| 指标 | 名称 | kind | 单位 | 参数 | 口径 | 数据源链 |")
        lines.append("| :- | :- | :-: | :-: | :- | :- | :- |")
        for m in ms:
            alias = f"<br>`{'/'.join(m.aliases)}`" if m.aliases else ""
            name = m.name if m.status == "ok" else f"~~{m.name}~~ ⚠️上游已下线"
            lines.append(
                f"| `{m.id}`{alias} | {name} | {m.kind} | {m.unit or '-'} | "
                f"{fmt_args(m.args)} | {fmt_calibrations(m.calibrations)} | {fmt_chain(m.providers)} |"
            )
        lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {out} ({len(cat.metrics)} metrics, {len(lines)} lines)")


if __name__ == "__main__":
    main()
