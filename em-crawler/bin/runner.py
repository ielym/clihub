#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""em-crawler CLI runner —— 把 CLI 命令分发到东方财富爬虫 adapter 方法。

由 bin/cli.js 调用：
    python runner.py <command> [--key value ...]

输出：stdout 上一行 JSON（成功）或错误信息（stderr，exit 1）。
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def _load_crawler():
    """动态定位 crawler 根目录并加入 sys.path。"""
    root = Path(__file__).resolve().parents[1]
    # 允许通过环境变量覆盖 crawler 位置
    override = Path(EM_CRAWLER_ROOT) if EM_CRAWLER_ROOT else None
    root = override or root
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # 确认 em_crawler 包可导入
    try:
        import em_crawler  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"无法导入 em_crawler（root={root}）：{e}\n"
            f"请通过环境变量 EM_CRAWLER_ROOT 指定爬虫根目录（含 em_crawler/ 的目录）。"
        )
    return root


# 在 import 前解析环境变量
EM_CRAWLER_ROOT = __import__("os").environ.get("EM_CRAWLER_ROOT", "")


def _to_jsonable(obj):
    """把 Envelope / pydantic / 任意对象转为可 JSON 序列化结构。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    # pydantic v2 model
    if hasattr(obj, "model_dump"):
        return _to_jsonable(obj.model_dump())
    if hasattr(obj, "dict"):
        return _to_jsonable(obj.dict())
    # dataclass
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return _to_jsonable(dataclasses.asdict(obj))
    # 兜底：转字符串
    return str(obj)


# ── 命令分发表 ────────────────────────────────────
# 每条: (adapter_attr, method, arg_map, help)
# arg_map 把 CLI 参数名映射到方法参数名
COMMANDS = {
    # ── 行情 em_market ──
    "quote": ("market", "fetch_snapshot", {"code": "code", "market": "market"}, "个股实时快照"),
    "bar": ("market", "fetch_bars", {"code": "code", "market": "market", "klt": "klt", "fqt": "fqt", "lmt": "lmt"}, "K线数据"),
    "tick": ("market", "fetch_tick", {"code": "code", "market": "market", "ndays": "ndays"}, "逐笔/分时"),
    "orderbook": ("market", "fetch_orderbook", {"code": "code", "market": "market"}, "五档盘口"),
    "clist": ("market", "fetch_clist", {"fs": "fs", "page_size": "page_size", "page": "page"}, "板块/证券列表"),
    "orderbook-abnormal": ("market", "fetch_orderbook_abnormal", {"page_size": "page_size"}, "盘口异动"),

    # ── 跨市场 em_cross ──
    "cross-snapshot": ("cross", "fetch_snapshot", {"secid": "secid"}, "跨市场快照(港股/美股等)"),
    "cross-bars": ("cross", "fetch_bars", {"secid": "secid", "klt": "klt", "fqt": "fqt", "lmt": "lmt"}, "跨市场K线"),
    "global-index": ("cross", "fetch_global_index", {}, "全球指数"),
    "bond-list": ("cross", "fetch_bond_list", {"page_size": "page_size"}, "可转债列表"),
    "bj": ("cross", "fetch_bj", {"page_size": "page_size"}, "北交所列表"),

    # ── 资金 em_money ──
    "moneyflow": ("money", "fetch_moneyflow", {"secid": "secid", "lmt": "lmt"}, "个股资金流向"),
    "lhb": ("money", "fetch_lhb", {"trade_date": "trade_date", "page_size": "page_size"}, "龙虎榜"),
    "lhb-seat": ("money", "fetch_lhb_seat", {"code": "code", "trade_date": "trade_date", "page_size": "page_size"}, "龙虎榜营业部"),
    "margin-sum": ("money", "fetch_margin_sum", {"page_size": "page_size"}, "两融余额汇总"),
    "margin-stock": ("money", "fetch_margin_stock", {"code": "code", "page_size": "page_size"}, "个股两融"),
    "hsgt": ("money", "fetch_hsgt", {"page_size": "page_size"}, "沪深港通资金"),
    "hsgt-quota": ("money", "fetch_hsgt_quota", {"page_size": "page_size"}, "北向资金额度"),
    "block-trade": ("money", "fetch_block_trade", {"code": "code", "page_size": "page_size"}, "大宗交易"),
    "pledge": ("money", "fetch_pledge", {"code": "code", "page_size": "page_size"}, "股权质押"),
    "pledge-ratio": ("money", "fetch_pledge_ratio", {"code": "code", "page_size": "page_size"}, "质押比例"),
    "holder-num": ("money", "fetch_holder_num", {"code": "code", "page_size": "page_size"}, "股东户数"),
    "account-stat": ("money", "fetch_account_stat", {"page_size": "page_size"}, "股票账户统计"),

    # ── 财务 em_finance ──
    "finance": ("finance", "fetch_indicators", {"code": "code", "report_date": "report_date", "page_size": "page_size"}, "财务指标(默认)"),
    "forecast": ("finance", "fetch_forecast", {"code": "code", "page_size": "page_size"}, "业绩预告"),
    "express": ("finance", "fetch_express", {"code": "code", "page_size": "page_size"}, "业绩快报"),
    "disclose-plan": ("finance", "fetch_disclose_plan", {"code": "code", "page_size": "page_size"}, "预约披露"),
    "balance": ("finance", "fetch_balance", {"code": "code", "page_size": "page_size"}, "资产负债表"),
    "income": ("finance", "fetch_income", {"code": "code", "page_size": "page_size"}, "利润表"),
    "cashflow": ("finance", "fetch_cashflow", {"code": "code", "page_size": "page_size"}, "现金流量表"),
    "dividend": ("finance", "fetch_dividend", {"code": "code", "page_size": "page_size"}, "分红送配"),
    "unlock": ("finance", "fetch_unlock", {"code": "code", "page_size": "page_size"}, "限售解禁"),
    "survey": ("finance", "fetch_survey", {"code": "code", "page_size": "page_size"}, "机构调研"),
    "rating": ("finance", "fetch_rating", {"code": "code", "begin": "begin", "page_size": "page_size"}, "评级/盈利预测"),

    # ── F10 em_f10 ──
    "f10-profile": ("f10", "fetch_profile", {"code": "code"}, "公司概况"),
    "f10-shareholders": ("f10", "fetch_shareholders", {"code": "code"}, "十大股东"),
    "f10-capital": ("f10", "fetch_capital", {"code": "code"}, "股本结构"),
    "f10-analysis": ("f10", "fetch_analysis", {"code": "code"}, "财务分析"),
    "f10-concept": ("f10", "fetch_concept", {"code": "code"}, "所属概念"),
    "f10-holding": ("f10", "fetch_holding", {"code": "code"}, "机构持股"),
    "f10-event": ("f10", "fetch_event", {"code": "code"}, "重大事项"),
    "f10-history-name": ("f10", "fetch_history_name", {"code": "code"}, "曾用名"),
    "f10-executives": ("f10", "fetch_executives", {"code": "code"}, "高管简历"),
    "f10-equity-incentive": ("f10", "fetch_equity_incentive", {"code": "code"}, "股权激励"),
    "f10-financing": ("f10", "fetch_financing", {"code": "code"}, "融资历史"),
    "f10-dividend-financing": ("f10", "fetch_dividend_financing", {"code": "code"}, "分红融资"),
    "f10-industry-compare": ("f10", "fetch_industry_compare", {"code": "code"}, "行业对比"),
    "f10-related": ("f10", "fetch_related", {"code": "code"}, "关联公司"),
    "f10-valuation": ("f10", "fetch_valuation", {"code": "code"}, "估值分析"),
    "f10-foreign": ("f10", "fetch_foreign", {"secucode": "secucode"}, "外资持股(需secucode)"),

    # ── 资讯 em_news ──
    "announcements": ("news", "fetch_announcements", {"ann_type": "ann_type", "page_size": "page_size"}, "公告列表"),
    "announcement-content": ("news", "fetch_announcement_content", {"art_code": "art_code"}, "公告正文"),
    "reports": ("news", "fetch_reports", {"code": "code", "q_type": "q_type", "page_size": "page_size"}, "研报列表"),
    "report-content": ("news", "fetch_report_content", {"info_code": "info_code"}, "研报正文"),
    "flash-news": ("news", "fetch_flash_news", {"page_size": "page_size", "fast_column": "fast_column"}, "快讯"),
    "news": ("news", "fetch_news", {"page_size": "page_size"}, "财经新闻"),
    "blog": ("news", "fetch_blog", {"page_size": "page_size"}, "博客"),
    "new-stock": ("news", "fetch_new_stock", {"page_size": "page_size"}, "新股"),
    "report-pdf": ("news", "fetch_report_pdf", {"info_code": "info_code", "title": "title"}, "研报PDF"),
    "periodic-report-pdf": ("news", "fetch_periodic_report_pdf", {"code": "code", "secucode": "secucode"}, "定期报告PDF"),
    "ipo-prospectus": ("news", "fetch_ipo_prospectus", {"code": "code"}, "IPO招股书"),

    # ── 基金 em_fund ──
    "fund-codes": ("fund", "fetch_fund_codes", {}, "基金代码表"),
    "fund-nav": ("fund", "fetch_fund_nav", {"code": "code", "page_size": "page_size"}, "基金净值"),
    "fund-holding": ("fund", "fetch_fund_holding", {"code": "code", "topline": "topline"}, "基金持仓"),
    "fund-manager": ("fund", "fetch_fund_manager", {"code": "code"}, "基金经理"),
    "fund-rank": ("fund", "fetch_fund_rank", {"dt": "dt", "page_size": "page_size"}, "基金排行"),
    "etf-lof": ("fund", "fetch_etf_lof", {"page_size": "page_size"}, "ETF/LOF"),
    "fund-report-pdf": ("fund", "fetch_fund_report_pdf", {"fund_code": "fund_code", "page_size": "page_size"}, "基金定期报告PDF"),

    # ── 宏观 em_macro ──
    "macro": ("macro", "fetch_domestic", {"indicator": "indicator", "page_size": "page_size"}, "国内宏观指标(CPI/PPI/PMI/GDP/M2/LPR/FISCAL/HOUSE_PRICE/SHZR/FOREX_RESERVE/ELECTRICITY)"),
    "macro-overseas": ("macro", "fetch_overseas", {"economy": "economy", "page_size": "page_size"}, "海外宏观(USANEW/EURONEW/CA/HK等)"),
    "industry-index": ("macro", "fetch_industry_index", {"page_size": "page_size", "page": "page"}, "行业板块"),
    "concept-board": ("macro", "fetch_concept_board", {"page_size": "page_size", "page": "page"}, "概念板块"),

    # ── 股吧 em_guba ──
    "guba-posts": ("guba", "fetch_posts", {"code": "code", "page": "page", "limit": "limit"}, "股吧帖子"),
    "guba-post": ("guba", "fetch_post_content", {"code": "code", "post_id": "post_id"}, "帖子正文"),
    "guba-comments": ("guba", "fetch_comments", {"code": "code", "post_id": "post_id", "page": "page"}, "帖子评论"),
    "guba-rank": ("guba", "fetch_rank", {"ps": "ps"}, "股吧热度排行"),

    # ── 工具 em_tools ──
    "screener": ("tools", "fetch_stock_screener", {"conditions": "conditions", "page_size": "page_size"}, "选股器"),
    "interactive": ("tools", "fetch_interactive", {"code": "code", "page_size": "page_size"}, "互动易"),
    "main-monitor": ("tools", "fetch_main_monitor", {"page_size": "page_size"}, "主力监控"),
    "index-valuation": ("tools", "fetch_index_valuation", {}, "指数估值"),
    "diagnosis": ("tools", "fetch_stock_diagnosis", {"code": "code"}, "个股诊断评分"),
    "fund-calc": ("tools", "fetch_fund_calculator", {"fund_code": "fund_code", "monthly_amount": "monthly_amount", "months": "months", "annual_rate": "annual_rate"}, "基金定投计算器"),
    "backtest": ("tools", "fetch_portfolio_backtest", {"weights": "weights", "period_returns": "period_returns"}, "组合回测"),
    "finance-infographic": ("tools", "fetch_finance_infographic", {"code": "code"}, "财报图解"),
}


def _parse_args(argv):
    """解析 CLI 参数：第一个位置参数为 command，其余 --key value。"""
    if not argv:
        return None, {}
    command = argv[0]
    kwargs = {}
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            key = tok[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                kwargs[key] = argv[i + 1]
                i += 2
            else:
                kwargs[key] = True
                i += 1
        else:
            # 位置参数：按命令约定映射到第一个参数
            kwargs.setdefault("_positional", tok)
            i += 1
    return command, kwargs


def _origin(t):
    """获取泛型的原始类型，如 dict[str,float] -> dict。"""
    import typing
    origin = typing.get_origin(t)
    return origin if origin is not None else t


def _coerce(value, target_type):
    """把 CLI 字符串值转为目标类型。"""
    origin = _origin(target_type)
    if origin is str:
        return value
    if origin is int:
        return int(value)
    if origin is float:
        return float(value)
    if origin is bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "y")
    if origin in (list, dict, tuple, set):
        return json.loads(value)
    return value


def _get_method_sig(adapter, method_name):
    """获取方法参数签名，用于类型推断。

    用 typing.get_type_hints 解析字符串注解（from __future__ import annotations）。
    """
    import inspect
    import typing
    method = getattr(adapter, method_name)
    try:
        hints = typing.get_type_hints(method)
    except Exception:
        hints = {}
    sig = inspect.signature(method)
    params = {}
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        params[name] = hints.get(name, str)
    return params


def _apply_positional(command, kwargs, adapter, method_name):
    """把位置参数绑定到方法的第一个参数。"""
    pos = kwargs.pop("_positional", None)
    if pos is None:
        return
    sig = _get_method_sig(adapter, method_name)
    if not sig:
        return
    first_param = next(iter(sig))
    # 不要覆盖已显式指定的同名参数
    if first_param not in kwargs:
        kwargs[first_param] = pos


def _run_command(command, kwargs):
    root = _load_crawler()
    from em_crawler.config.config import settings
    settings.ensure_dirs()
    from em_crawler.adapter.anti_bot import AntiBotClient
    from em_crawler.adapter.em_market import EmMarketAdapter
    from em_crawler.adapter.em_cross import EmCrossAdapter
    from em_crawler.adapter.em_money import EmMoneyAdapter
    from em_crawler.adapter.em_finance import EmFinanceAdapter
    from em_crawler.adapter.em_f10 import EmF10Adapter
    from em_crawler.adapter.em_news import EmNewsAdapter
    from em_crawler.adapter.em_fund import EmFundAdapter
    from em_crawler.adapter.em_macro import EmMacroAdapter
    from em_crawler.adapter.em_guba import EmGubaAdapter
    from em_crawler.adapter.em_tools import EmToolsAdapter

    client = AntiBotClient()
    adapters = {
        "market": EmMarketAdapter(client),
        "cross": EmCrossAdapter(client),
        "money": EmMoneyAdapter(client),
        "finance": EmFinanceAdapter(client),
        "f10": EmF10Adapter(client),
        "news": EmNewsAdapter(client),
        "fund": EmFundAdapter(client),
        "macro": EmMacroAdapter(client),
        "guba": EmGubaAdapter(client),
        "tools": EmToolsAdapter(client),
    }

    adapter_attr, method_name, arg_map, _ = COMMANDS[command]
    adapter = adapters[adapter_attr]
    _apply_positional(command, kwargs, adapter, method_name)

    # 类型转换
    sig = _get_method_sig(adapter, method_name)
    call_kwargs = {}
    for cli_key, value in kwargs.items():
        if cli_key not in arg_map:
            print(f"[warn] 未知参数 --{cli_key}，已忽略", file=sys.stderr)
            continue
        method_param = arg_map[cli_key]
        target_type = sig.get(method_param, str)
        try:
            call_kwargs[method_param] = _coerce(value, target_type)
        except Exception as e:
            print(f"[error] 参数 --{cli_key}={value!r} 转换失败：{e}", file=sys.stderr)
            sys.exit(1)

    method = getattr(adapter, method_name)
    result = method(**call_kwargs)
    return result


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_help_text())
        return
    if argv[0] in ("-v", "--version", "version"):
        print("em-crawler 1.0.0")
        return
    if argv[0] == "list":
        for cmd, (_, _, _, help_) in COMMANDS.items():
            print(f"  {cmd:30s} {help_}")
        return

    command, kwargs = _parse_args(argv)
    if command not in COMMANDS:
        print(f"未知命令：{command}", file=sys.stderr)
        print("用 em-crawler list 查看所有命令", file=sys.stderr)
        sys.exit(1)

    try:
        result = _run_command(command, kwargs)
        print(json.dumps(_to_jsonable(result), ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def _help_text():
    lines = [
        "em-crawler —— 东方财富全量采集 CLI",
        "",
        "用法:",
        "  em-crawler <command> [--key value ...]",
        "  em-crawler list                  列出所有命令",
        "  em-crawler <command> --help      查看命令说明",
        "",
        "环境变量:",
        "  EM_CRAWLER_ROOT   爬虫根目录（含 em_crawler/ 的目录），默认自动探测",
        "  EM_CRAWLER_PYTHON Python 解释器路径，默认用 node 查找的 python",
        "",
        "常用命令:",
    ]
    common = ["quote", "bar", "f10-profile", "finance", "moneyflow", "macro", "diagnosis", "hsgt", "fund-nav"]
    for cmd in common:
        if cmd in COMMANDS:
            _, _, _, help_ = COMMANDS[cmd]
            lines.append(f"  {cmd:30s} {help_}")
    lines.append("")
    lines.append("用 em-crawler list 查看全部命令。")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
