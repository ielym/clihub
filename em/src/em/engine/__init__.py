"""查询引擎：意图查询 → 分组规划 → provider 兜底 → 字段提取 → 干净结果。

- 单指标：按 provider 优先级尝试，命中即停（兜底链）。
- 批量：按 (endpoint, args) 分组合并请求（同一接口一次拿多字段）。
"""
from __future__ import annotations

from typing import Any

from em.catalog import Catalog, Metric, ProviderRef
from em.client import HttpClient
from em.providers import _secid, _secucode, _market
from em.providers.registry import ENDPOINTS

_ADJUST_FQT = {"none": 0, "qfq": 1, "hfq": 2}


def register_endpoints(mapping: dict[str, Any]) -> None:
    ENDPOINTS.update(mapping)


class QueryResult:
    __slots__ = ("metric", "calibration", "value", "unit", "as_of", "provider", "fallback")

    def __init__(self, metric, calibration, value, unit, as_of, provider, fallback):
        self.metric = metric
        self.calibration = calibration
        self.value = value
        self.unit = unit
        self.as_of = as_of
        self.provider = provider
        self.fallback = fallback

    def to_dict(self) -> dict:
        return {
            "metric": self.metric, "calibration": self.calibration,
            "value": self.value, "unit": self.unit, "as_of": self.as_of,
            "provider": self.provider, "fallback": self.fallback,
        }


class Engine:
    def __init__(self, catalog: Catalog, client: HttpClient | None = None):
        self.catalog = catalog
        self.client = client or HttpClient()

    # ---- 意图解析 ----
    def resolve(self, name: str) -> Metric:
        m = self.catalog.get(name)
        if m is None:
            raise ValueError(f"未知指标：{name}（可用 `em list` 查看全部指标）")
        return m

    def _context(self, query: dict, metric: Metric) -> dict:
        """把查询参数 + 口径 + 派生物构造成 endpoint 可用的上下文。"""
        ctx: dict[str, Any] = {name: None for name in metric.args}
        ctx.update({name: None for name in metric.calibrations})
        ctx.update(query)
        for cname, cspec in metric.calibrations.items():
            if ctx.get(cname) is None:
                ctx[cname] = cspec.get("default")
            # 口径 → 源字段映射：pe 的 scope → pe_ttm/pe_dynamic/pe_static
            maps = cspec.get("maps") or {}
            if maps:
                ctx[f"{cname}_field"] = maps.get(ctx[cname], maps.get(cspec.get("default")))
        code = query.get("code") or ""
        if code:
            ctx["secid"] = _secid(code)
            ctx["secucode"] = _secucode(code)
            ctx["market"] = _market(code)
        if ctx.get("adjust") is not None:
            ctx["fqt"] = _ADJUST_FQT.get(ctx["adjust"], 0)
        return ctx

    def _resolve_args(self, provider: ProviderRef, ctx: dict) -> dict:
        out = {}
        for k, v in provider.args.items():
            if isinstance(v, str) and v in ctx:
                val = ctx[v]
            elif isinstance(v, str) and v.startswith("@") and v[1:] in ctx:
                val = ctx[v[1:]]
            elif isinstance(v, str) and "{" in v:
                val = self._resolve_field(v, ctx)
            else:
                val = v
            if val is not None:      # 可选参数缺省 → 跳过，让 endpoint 用自身默认值
                out[k] = val
        return out

    @staticmethod
    def _resolve_field(field: str, ctx: dict) -> str:
        """解析字段模板："{scope_field}" → 实际源字段名。"""
        if not field or "{" not in field:
            return field
        import re
        def repl(m):
            return str(ctx.get(m.group(1), ""))
        return re.sub(r"\{(\w+)\}", repl, field)

    def _extract(self, result: Any, provider: ProviderRef) -> Any:
        if isinstance(result, list):
            if provider.row == "all":
                out = []
                for r in result:
                    if isinstance(r, dict):
                        out.append(r.get(provider.field) if provider.field else r)
                    else:
                        out.append(r)
                return out
            if provider.row == "first":
                idx = 0
            elif provider.row == "last":
                idx = -1
            else:
                idx = int(provider.row)
            if not result:
                return None
            r = result[idx]
            if isinstance(r, dict):
                return r.get(provider.field) if provider.field else r
            return r
        if isinstance(result, dict):
            return result.get(provider.field) if provider.field else result
        return result

    # ---- 单指标查询 ----
    def query(self, name: str, args: dict | None = None) -> QueryResult:
        args = args or {}
        metric = self.resolve(name)
        ctx = self._context(args, metric)
        errors = []
        for prov in sorted(metric.providers, key=lambda p: p.priority):
            fn = ENDPOINTS.get(prov.endpoint)
            if fn is None:
                errors.append(f"{prov.endpoint}:未注册")
                continue
            kwargs = self._resolve_args(prov, ctx)
            field = self._resolve_field(prov.field, ctx)
            prov = ProviderRef(endpoint=prov.endpoint, field=field, priority=prov.priority,
                               args=prov.args, row=prov.row, note=prov.note)
            try:
                result = fn(self.client, **kwargs)
            except Exception as e:  # 网络/限流异常 → 走兜底
                errors.append(f"{prov.endpoint}:{type(e).__name__}")
                continue
            value = self._extract(result, prov)
            if value in (None, "", "-", []):
                errors.append(f"{prov.endpoint}:空值")
                continue
            return QueryResult(
                metric=metric.id,
                calibration={k: ctx.get(k) for k in metric.calibrations},
                value=self._coerce(value, metric),
                unit=metric.unit, as_of=self._as_of(result, prov, ctx),
                provider=prov.endpoint, fallback=prov.priority > 1,
            )
        raise RuntimeError(f"指标 {metric.id} 当前不可用（{'; '.join(errors) or '无 provider'}）")

    def _coerce(self, value, metric: Metric):
        if metric.value_type == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                return value
        if metric.value_type == "int":
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return value
        return value

    def _as_of(self, result, prov: ProviderRef, ctx: dict) -> Any:
        # 从结果里找时间字段（date/trade_date/report_date…），或回退 trade_date 参数
        if isinstance(result, list) and result:
            last = result[-1]
            if isinstance(last, dict):
                for k in ("date", "trade_date", "report_date", "nav_date", "time"):
                    if k in last:
                        return last[k]
        if isinstance(result, dict):
            for k in ("date", "trade_date", "report_date", "nav_date", "time", "exact_time"):
                if k in result:
                    return result[k]
        return ctx.get("trade_date")

    # ---- 批量查询（同 endpoint 合并请求）----
    def batch(self, specs: list[tuple[str, dict]]) -> list[QueryResult]:
        """批量查询：按 (endpoint, 参数签名) 分组合并请求，一次接口拿多字段。"""
        results: list[QueryResult] = []
        groups: dict[tuple, list] = {}
        order: list[tuple] = []
        for name, args in specs:
            metric = self.resolve(name)
            ctx = self._context(args or {}, metric)
            prov = metric.primary()
            fn = ENDPOINTS.get(prov.endpoint)
            field = self._resolve_field(prov.field, ctx)
            rprov = ProviderRef(endpoint=prov.endpoint, field=field, priority=prov.priority,
                                args=prov.args, row=prov.row, note=prov.note)
            kwargs = self._resolve_args(prov, ctx)
            sig = tuple(sorted((k, str(v)) for k, v in kwargs.items()))
            key = (prov.endpoint, sig)
            entry = (metric, ctx, rprov, fn, kwargs)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(entry)

        for key in order:
            entries = groups[key]
            fn = entries[0][3]
            kwargs = entries[0][4]
            try:
                result = fn(self.client, **kwargs)
            except Exception:
                result = None
            for metric, ctx, rprov, _fn, _kw in entries:
                value = self._extract(result, rprov) if result is not None else None
                if value in (None, "", "-", []):
                    results.append(self._fallback_query(metric, ctx, skip=rprov.endpoint))
                else:
                    results.append(QueryResult(
                        metric=metric.id,
                        calibration={k: ctx.get(k) for k in metric.calibrations},
                        value=self._coerce(value, metric),
                        unit=metric.unit, as_of=self._as_of(result, rprov, ctx),
                        provider=rprov.endpoint, fallback=False))
        return results

    def _fallback_query(self, metric: Metric, ctx: dict, skip: str) -> QueryResult:
        """主源失败后按兜底链重试（跳过已失败的 endpoint）。"""
        errors = []
        for prov in sorted(metric.providers, key=lambda p: p.priority):
            if prov.endpoint == skip:
                continue
            fn = ENDPOINTS.get(prov.endpoint)
            if fn is None:
                continue
            try:
                result = fn(self.client, **self._resolve_args(prov, ctx))
            except Exception as e:
                errors.append(f"{prov.endpoint}:{type(e).__name__}")
                continue
            prov = ProviderRef(endpoint=prov.endpoint, field=self._resolve_field(prov.field, ctx),
                               priority=prov.priority, args=prov.args, row=prov.row, note=prov.note)
            value = self._extract(result, prov)
            if value in (None, "", "-", []):
                errors.append(f"{prov.endpoint}:空值")
                continue
            return QueryResult(
                metric=metric.id, calibration={k: ctx.get(k) for k in metric.calibrations},
                value=self._coerce(value, metric), unit=metric.unit,
                as_of=self._as_of(result, prov, ctx), provider=prov.endpoint, fallback=True)
        raise RuntimeError(f"指标 {metric.id} 当前不可用（{'；'.join(errors) or '无 provider'}）")