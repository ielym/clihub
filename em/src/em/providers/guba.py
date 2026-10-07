"""股吧 Provider：帖子列表 / 正文 / 评论 / 热度排行（含 AES 解密）。"""
from __future__ import annotations

import base64
import json
import re
from html import unescape

GUBA_REFERER = "https://guba.eastmoney.com/"
LIST_URL = "https://guba.eastmoney.com/list,{code}.html"
POST_URL = "https://guba.eastmoney.com/news,{code},{post_id}.html"
COMMENT_API = "https://gbcdn.dfcfw.com/gbapi/reply_api_Reply_ArticleNewReplyList.js"
RANK_API = "https://gbcdn.dfcfw.com/rank/popularityList.js"


def guba_posts(client, code: str, page: int = 1, limit: int = 20, **kw) -> list[dict]:
    url = LIST_URL.format(code=code) if page <= 1 else f"{LIST_URL.format(code=code)[:-5]}_{page}.html"
    html = client.get_text(url, referer=GUBA_REFERER)
    data = _var_json(html, "article_list") or {}
    rows = data.get("re") or []
    out = []
    for r in rows[:limit]:
        u = r.get("user") or {}
        out.append({"post_id": r.get("post_id"), "title": r.get("post_title"),
                    "bar_code": r.get("stockbar_code"), "bar_name": r.get("stockbar_name"),
                    "user": u.get("user_nickname") if isinstance(u, dict) else r.get("user_nickname"),
                    "click_count": r.get("post_click_count"),
                    "comment_count": r.get("post_comment_count"),
                    "publish_time": r.get("post_publish_time"),
                    "bullish_bearish": r.get("bullish_bearish"), "post_type": r.get("post_type")})
    return out


def guba_post_content(client, code: str, post_id: str, **kw) -> dict:
    html = client.get_text(POST_URL.format(code=code, post_id=post_id), referer=GUBA_REFERER)
    data = _var_json(html, "post_article") or {}
    u = data.get("post_user") or {}
    return {"post_id": data.get("post_id"), "title": data.get("post_title"),
            "content": _strip_html(data.get("post_content") or ""),
            "user": u.get("user_nickname"), "publish_time": data.get("post_publish_time"),
            "click_count": data.get("post_click_count"), "like_count": data.get("post_like_count")}


def guba_comments(client, code: str, post_id: str, page: int = 1, ps: int = 20, **kw) -> list[dict]:
    txt = client.get_text(COMMENT_API, params={"postid": post_id, "ps": ps, "p": page, "sorttype": 1},
                          referer=GUBA_REFERER)
    data = _var_json(txt, "reply_api_Reply_ArticleNewReplyList") or {}
    out = []
    for r in (data.get("re") or []):
        u = r.get("reply_user") or {}
        out.append({"reply_id": r.get("reply_id"), "post_id": post_id,
                    "user": u.get("user_nickname"),
                    "content": _strip_html(r.get("reply_text") or ""),
                    "publish_time": r.get("reply_publish_time"),
                    "like_count": r.get("reply_like_count")})
    return out


_RANK_KEY = b"ae13e0ad97cdd6e12408ac5063d88721"
_RANK_IV = b"getClassFromFile"


def guba_rank(client, ps: int = 10, **kw) -> list[dict]:
    txt = client.get_text(RANK_API, params={"type": 0, "sort": 0, "page": 1, "ps": ps,
                                            "v": __import__("datetime").datetime.now().strftime("%Y-%m-%d-%H") + "-0"},
                          referer=GUBA_REFERER)
    raw = _var_str(txt, "popularityList") or ""
    rows = _decrypt_rank(raw)[:ps]
    out = []
    for r in rows:
        hist = r.get("history") or []
        last = hist[-1] if hist else {}
        out.append({"rank": r.get("rankNumber"), "code": str(r.get("code")),
                    "change_number": r.get("changeNumber"), "exact_time": r.get("exactTime"),
                    "new_fans": r.get("newFans"), "iron_fans": r.get("ironsFans"),
                    "heat": last.get("HOTRANKSCORE"), "market_count": last.get("MARKETALLCOUNT"),
                    "security_market": last.get("SRCSECURITYCODE")})
    return out


def _decrypt_rank(raw: str) -> list[dict]:
    if not raw:
        return []
    try:
        from Crypto.Cipher import AES
        ct = base64.b64decode(raw)
        pt = AES.new(_RANK_KEY, AES.MODE_CBC, _RANK_IV).decrypt(ct)
        pad = pt[-1] if pt else 0
        if not (1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad):
            return []
        data = json.loads(pt[:-pad].decode("utf-8", errors="ignore"))
        return data if isinstance(data, list) else (data.get("re") or [])
    except Exception:
        return []


def _var_json(html: str, var: str):
    s = _var_str(html, var)
    if not s:
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _var_str(html: str, var: str):
    m = re.search(rf"var\s+{re.escape(var)}\s*=\s*", html)
    if not m:
        return None
    i = m.end()
    while i < len(html) and html[i] in " \t":
        i += 1
    ch = html[i]
    if ch in "[{":
        return _bracket(html, i)
    if ch in "\"'":
        return _quote(html, i)
    j = i
    while j < len(html) and html[j] not in ";,":
        j += 1
    return html[i:j].strip()


def _bracket(s, start):
    stack, in_str, esc = [], None, False
    pairs = {"}": "{", "]": "["}
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == in_str:
                in_str = None
            continue
        if c in "\"'":
            in_str = c
        elif c in "[{":
            stack.append(c)
        elif c in "]}":
            if stack and stack[-1] == pairs[c]:
                stack.pop()
                if not stack:
                    return s[start:i + 1]
    return None


def _quote(s, start):
    q = s[start]
    i, esc = start + 1, False
    while i < len(s):
        c = s[i]
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c == q:
            return s[start:i + 1]
        i += 1
    return None


def _strip_html(v):
    v = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", v, flags=re.S)
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", unescape(v)).strip()


ENDPOINTS = {
    "guba.posts": guba_posts,
    "guba.post_content": guba_post_content,
    "guba.comments": guba_comments,
    "guba.rank": guba_rank,
}