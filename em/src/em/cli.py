"""em CLI 入口：意图查询东方财富数据。

用法：
  em <指标> <代码> [--口径/参数 ...]
  em list [--group 行情]
  em batch <代码> <指标1>,<指标2>,...
"""
from __future__ import annotations

import json
import sys


def _main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        _emit(_help())
        return
    if argv[0] == "list":
        _list(argv[1:])
        return

    from em.catalog import load
    from em.engine import Engine
    from em.client import HttpClient

    catalog = load()
    engine = Engine(catalog, HttpClient())

    if argv[0] == "batch":
        _batch(engine, argv[1:])
        return

    metric = argv[0]
    positional = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else ""
    args = _parse_flags(argv[2:] if positional else argv[1:])
    if positional:
        # 位置参数名：多数指标是 code；标的/合约/板块/日期类指标按其唯一必填参数名绑定
        m = catalog.get(metric)
        req = [k for k, v in (m.args if m else {}).items()
               if isinstance(v, dict) and v.get("required") and k != "code"]
        if m is not None and "code" not in m.args and len(req) == 1:
            args[req[0]] = positional
        else:
            args["code"] = positional
    try:
        result = engine.query(metric, args)
    except Exception as e:
        _fail(e)
        return
    _emit({"ok": True, **result.to_dict()})


def _parse_flags(tokens: list[str]) -> dict:
    out: dict = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok[2:].replace("-", "_")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                out[key] = tokens[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            i += 1
    return out


def _batch(engine, args: list[str]) -> None:
    if not args:
        _fail("batch 用法：em batch <代码> <指标1>,<指标2>,...")
        return
    code = args[0]
    metrics = args[1].split(",") if len(args) > 1 else []
    flags = _parse_flags(args[2:])
    specs = [(m, {"code": code, **flags}) for m in metrics]
    try:
        results = [r.to_dict() for r in engine.batch(specs)]
        _emit({"ok": True, "code": code, "results": results})
    except Exception as e:
        _fail(e)


def _list(args: list[str]) -> None:
    from em.catalog import load
    catalog = load()
    group = None
    for i, a in enumerate(args):
        if a == "--group" and i + 1 < len(args):
            group = args[i + 1]
    metrics = catalog.by_group(group) if group else catalog.all()
    out = {
        "ok": True,
        "count": len(metrics),
        "groups": catalog.groups,
        "metrics": [
            {"id": m.id, "name": m.name, "group": m.group, "kind": m.kind,
             "unit": m.unit, "aliases": m.aliases,
             "calibrations": list(m.calibrations.keys())}
            for m in sorted(metrics, key=lambda x: (x.group, x.id))
        ],
    }
    _emit(out)


def _help():
    return {
        "ok": True,
        "name": "em",
        "version": "2.0.0",
        "usage": [
            "em list                               列出全部指标（意图）",
            "em <指标> <代码> [--参数 --口径 ...]     查询单一指标（干净单值）",
            "em batch <代码> 指标1,指标2,...         批量合并查询",
            "em <指标> <代码> --trade_date YYYY-MM-DD --adjust qfq",
            "em pe 000001 --scope ttm",
        ],
        "说明": "使用导向：按数据意图查询，返回干净、口径明确的单一指标。",
    }


def _emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _fail(e) -> None:
    _emit({"ok": False, "error": str(e)})


if __name__ == "__main__":
    _main(sys.argv[1:])