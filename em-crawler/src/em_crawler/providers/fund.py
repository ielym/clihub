"""基金 Provider：代码表 / 净值 / 持仓 / 经理 / 排行 / ETF/LOF / 定期报告 PDF。"""
from __future__ import annotations

import datetime
import json
import re

FUND_CODES = "https://fund.eastmoney.com/js/fundcode_search.js"
FUND_NAV = "https://api.fund.eastmoney.com/f10/lsjz"
FUND_ARCHIVE = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
FUND_REFERER = "http://fundf10.eastmoney.com/"


def fund_codes(client, page_size: int = 20, **kw) -> list[dict]:
    txt = client.get_text(FUND_CODES, referer="https://fund.eastmoney.com/")
    body = _js_var_json(txt, "r")
    rows = json.loads(body) if body else []
    out = []
    for r in rows[:page_size]:
        out.append({"fund_code": r[0], "pinyin": r[1], "name": r[2],
                    "fund_type": r[3], "full_name": r[4]})
    return out


def fund_nav(client, code: str, page_size: int = 5, **kw) -> list[dict]:
    j = client.get_json(FUND_NAV, params={"fundCode": code, "pageIndex": 1, "pageSize": page_size}, referer=FUND_REFERER)
    return [{"fund_code": code, **r} for r in ((j.get("Data") or {}).get("LSJZList") or [])]


def fund_holding(client, code: str, topline: int = 10, **kw) -> list[dict]:
    txt = client.get_text(FUND_ARCHIVE, params={"type": "jjcc", "code": code, "topline": topline}, referer=FUND_REFERER)
    html = _extract_content(txt)
    return [{"fund_code": code, "table": t} for t in _parse_tables(html)]


def fund_manager(client, code: str, **kw) -> dict:
    html = client.get_text(f"http://fundf10.eastmoney.com/jjjl_{code}.html", referer=FUND_REFERER)
    managers = _extract_managers(html)
    return {"fund_code": code, "managers": managers, "manager_count": len(managers)}


def fund_rank(client, dt: str = "kf", page_size: int = 20, **kw) -> list[dict]:
    today = datetime.date.today()
    sd = (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    ed = today.strftime("%Y-%m-%d")
    txt = client.get_text("https://fund.eastmoney.com/data/rankhandler.aspx",
                          params={"op": "ph", "dt": dt, "ft": "all", "sc": "zzf", "st": "desc",
                                  "sd": sd, "ed": ed, "pi": 1, "pn": page_size, "dx": 1, "v": "0.1"},
                          referer="https://fund.eastmoney.com/")
    body = _js_var_json(txt, "rankData")
    data = json.loads(body) if body else {}
    out = []
    for s in (data.get("datas") or [])[:page_size]:
        p = s.split(",")
        if len(p) < 16:
            continue
        out.append({"fund_code": p[0], "name": p[1], "nav_date": p[3],
                    "unit_nav": p[4], "acc_nav": p[5], "daily_growth": p[6],
                    "week_growth": p[7], "month_growth": p[8], "month3_growth": p[9],
                    "month6_growth": p[10], "year_growth": p[11], "ytd_growth": p[14],
                    "since_inception": p[15]})
    return out


def fund_report_pdf(client, fund_code: str, page_size: int = 5, **kw) -> list[dict]:
    raw = client.get_text("https://fundf10.eastmoney.com/F10DataApi.aspx",
                          params={"type": "jjgg", "code": fund_code, "page": 1, "per": page_size * 3},
                          referer=f"https://fundf10.eastmoney.com/jjgg_{fund_code}.html")
    m = re.search(r'content\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if not m:
        return []
    table_html = m.group(1).replace('\\/', '/').replace('\\"', '"').replace("\\'", "'")
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        pdfm = re.search(r'class=[\'"]pdf[\'"][^>]*href=[\'"]([^\'"]+)', tr)
        pdf_url = pdfm.group(1) if pdfm else ""
        if pdf_url.startswith("//"):
            pdf_url = "https:" + pdf_url
        a = re.findall(r"<a[^>]*>(.*?)</a>", tr, re.S)
        title = re.sub(r"<[^>]+>", "", a[0]).strip() if a else ""
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", tr)
        if title or pdf_url:
            out.append({"fund_code": fund_code, "title": title, "attach_url": pdf_url,
                        "notice_date": dm.group(1) if dm else None})
        if len(out) >= page_size:
            break
    return out


def _js_var_json(txt: str, var: str):
    m = re.search(rf"var\s+{var}\s*=\s*(.*?);?\s*$", txt, re.S)
    if not m:
        return None
    s = m.group(1).strip()
    s = re.sub(r'([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s


def _extract_content(txt: str) -> str:
    m = re.search(r'content\s*:\s*"((?:[^"\\]|\\.)*)"', txt)
    return m.group(1).replace("\\/", "/").replace('\\"', '"') if m else ""


def _parse_tables(html: str, max_tables: int = 4) -> list[list[list[str]]]:
    tables = []
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", html, re.S):
        if len(tables) >= max_tables:
            break
        rows = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", rm.group(1), re.S)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def _extract_managers(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]*class="[^"]*manager[^"]*"[^>]*>([^<]+)</a>', html):
        out.append({"name": m.group(1).strip()})
    return out


def fund_dividend(client, code: str, max_tables: int = 6, **kw) -> list[dict]:
    """基金分红送配 / 拆分折算（fundf10 fhsp 页表格，含年份/权益登记日/每份分红/拆分比例）。"""
    html = client.get_text(f"http://fundf10.eastmoney.com/fhsp_{code}.html", referer=FUND_REFERER)
    tables = _parse_tables(html, max_tables=max_tables)
    out = []
    for t in tables:
        header = t[0] if t else []
        head = "".join(header) if header else ""
        # 只保留分红/拆分正文表（表头含 年份/登记日/除息/分红/拆分）
        if not any(k in head for k in ("年份", "权益登记", "除息", "分红", "拆分", "折算")):
            continue
        for row in t[1:]:
            cells = [c for c in row if c]
            if cells:
                out.append({"fund_code": code, "section": header[0].strip() if header else "",
                            "rows": cells})
    return out


def fund_rating(client, page_size: int = 20, **kw) -> list[dict]:
    """基金评级（fund.eastmoney.com/data/fundrating.html 内嵌 fundinfos 管道串）。"""
    html = client.get_text("https://fund.eastmoney.com/data/fundrating.html",
                           referer="https://fund.eastmoney.com/")
    m = re.search(r'var\s+fundinfos\s*=\s*"([\s\S]*?)";', html)
    if not m:
        return []
    body = m.group(1)
    limit = int(page_size) if page_size else 20
    out = []
    for rec in body.split("_")[:limit * 2]:
        f = rec.split("|")
        if len(f) < 7:
            continue
        out.append({"fund_code": f[0], "name": f[1], "fund_type": f[2],
                    "manager": f[3], "company": f[5], "company_id": f[6],
                    "ratings": [x for x in f[7:17]]})
        if len(out) >= limit:
            break
    return out


def fund_company(client, page_size: int = 20, **kw) -> list[dict]:
    """基金公司列表/排名（fund.eastmoney.com/Company/home/gspmlist 服务端表格）。"""
    html = client.get_text("https://fund.eastmoney.com/Company/home/gspmlist",
                           referer="http://fund.eastmoney.com/company/default.html")
    tables = _parse_tables(html, max_tables=1)
    if not tables:
        return []
    t = tables[0]
    header = [c for c in (t[0] if t else []) if c]
    out = []
    for row in t[1:]:
        cells = [c for c in row if c]
        if cells:
            out.append(dict(zip([f"col{i}" for i in range(len(cells))], cells)))
    # 去掉表头重复行（表头已在 header）
    return (out if header else out)[: int(page_size)]


ENDPOINTS = {
    "fund.codes": fund_codes,
    "fund.nav": fund_nav,
    "fund.holding": fund_holding,
    "fund.manager": fund_manager,
    "fund.rank": fund_rank,
    "fund.report_pdf": fund_report_pdf,
    "fund.dividend": fund_dividend,
    "fund.rating": fund_rating,
    "fund.company": fund_company,
}