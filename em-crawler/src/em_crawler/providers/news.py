"""资讯 Provider：公告 / 研报 / 快讯 / 财经新闻 / 新股 / 原文 PDF。"""
from __future__ import annotations

import datetime
import hashlib
import re
from html import unescape

ANN_LIST = "https://np-anotice-stock.eastmoney.com/api/security/ann"
ANN_CONTENT = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
REPORT_LIST = "https://reportapi.eastmoney.com/report/list"
FLASH_NEWS = "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
FINANCE_HOME = "https://finance.eastmoney.com/"
DATA_REFERER = "https://data.eastmoney.com/"


def announcements(client, ann_type: str = "A", page_size: int = 10, **kw) -> list[dict]:
    j = client.get_json(ANN_LIST,
                        params={"sr": -1, "page_size": page_size, "page_index": 1,
                                "ann_type": ann_type, "client_source": "web", "f_node": 0, "s_node": 0},
                        referer="https://data.eastmoney.com/notices/")
    rows = (j.get("data") or {}).get("list") or []
    return [{"art_code": r.get("art_code"), "title": r.get("title"),
             "notice_date": r.get("notice_date"), **r} for r in rows]


def announcement_content(client, art_code: str, **kw) -> dict:
    j = client.get_json(ANN_CONTENT,
                        params={"art_code": art_code, "client_source": "web", "page_index": 1},
                        referer="https://data.eastmoney.com/notices/")
    d = j.get("data") or {}
    d.setdefault("title", d.get("notice_title"))
    return d


def announcement_pdf(client, art_code: str, **kw) -> dict:
    """公告原文 PDF（含定期报告/招股书等公告附件）。"""
    d = announcement_content(client, art_code)
    return {"art_code": art_code, "title": d.get("notice_title"),
            "attach_url": d.get("attach_url"), "attach_size": d.get("attach_size"),
            "attach_list": d.get("attach_list") or d.get("attach_list_ch") or d.get("attach_list_en")}


def report_pdf(client, info_code: str, **kw) -> dict:
    """研报 PDF 原文（pdf.dfcfw.com H3 通道，由 info_code 映射）。"""
    return {"info_code": info_code,
            "attach_url": f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"}


def reports(client, q_type: int = 0, begin: str = "", end: str = "", page_size: int = 10, **kw) -> list[dict]:
    today = datetime.date.today()
    begin = begin or (today - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    end = end or today.strftime("%Y-%m-%d")
    j = client.get_json(REPORT_LIST,
                        params={"industryCode": "*", "pageSize": page_size, "industry": "*",
                                "rating": "", "ratingChange": "", "beginTime": begin,
                                "endTime": end, "pageNo": 1, "qType": q_type},
                        referer=DATA_REFERER)
    return j.get("data") or []


def report_content(client, info_code: str, **kw) -> dict:
    html = client.get_text(f"https://data.eastmoney.com/report/info/{info_code}.html", referer=DATA_REFERER)
    return {"info_code": info_code, "title": _title(html) or info_code,
            "body": _body(html)[:5000], "body_len": len(html)}


def flash_news(client, fast_column: str = "102", page_size: int = 10, **kw) -> list[dict]:
    j = client.get_json(FLASH_NEWS,
                        params={"client": "web", "biz": "web_724", "fastColumn": fast_column,
                                "sortEnd": "", "pageSize": page_size, "req_trace": str(int(__import__("time").time() * 1000))},
                        referer="https://kuaixun.eastmoney.com/")
    return (j.get("data") or {}).get("fastNewsList") or []


def news(client, page_size: int = 10, **kw) -> list[dict]:
    html = client.get_text(FINANCE_HOME, referer="https://www.eastmoney.com/")
    out = []
    for title, href in _news_links(html)[:page_size]:
        body = client.get_text(href, referer=FINANCE_HOME) if href.startswith("http") else ""
        out.append({"title": title, "url": href,
                    "body": _body(body)[:5000], "body_len": len(body)})
    return out


def _news_links(html: str) -> list[tuple[str, str]]:
    items = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{4,60})</a>', html):
        href, title = m.group(1), unescape(m.group(2)).strip()
        if href.startswith("http") and title:
            items.append((title, href))
    return items


def _title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    return unescape(m.group(1)).strip() if m else ""


def _body(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()


ENDPOINTS = {
    "news.announcements": announcements,
    "news.announcement_content": announcement_content,
    "news.announcement_pdf": announcement_pdf,
    "news.report_pdf": report_pdf,
    "news.reports": reports,
    "news.report_content": report_content,
    "news.flash": flash_news,
    "news.news": news,
}