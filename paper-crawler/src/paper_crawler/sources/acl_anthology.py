"""ACL Anthology 数据源。

来源：GitHub 仓库 acl-org/acl-anthology 的 XML 文件
URL：https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/{collection}.xml

输出为结构化论文信息（content_type="json"），不再透传原始 XML：
- source_id 使用官方 Anthology ID（如 2024.acl-long.1 / P19-1001）
- pdf_url 仅在论文在 Anthology 托管（XML 含 <pdf>）时给出，不猜测、不编造
- 站外出版方页面放入 external_urls，补充材料放入 attachments
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord

ANTHOLOGY_BASE = "https://aclanthology.org"


def _build_anthology_id(collection_id: str, volume_id: str, paper_id: str) -> str:
    """按官方规则拼接 Anthology ID（移植自 acl_anthology.utils.ids.build_id）。

    >>> _build_anthology_id("2024.acl", "long", "1")
    '2024.acl-long.1'
    >>> _build_anthology_id("P18", "1", "1")
    'P18-1001'
    >>> _build_anthology_id("W18", "63", "10")
    'W18-6310'
    """
    if collection_id[0].isdigit():
        # 2020 年后：{collection}-{volume}.{paper}
        return f"{collection_id}-{volume_id}.{paper_id}"
    # pre-2020：W*、C69、D19 卷号 >=5 时卷号与篇号均按两位补零
    if (
        collection_id.startswith("W")
        or collection_id == "C69"
        or (collection_id == "D19" and int(volume_id) >= 5)
    ):
        return f"{collection_id}-{int(volume_id):02d}{int(paper_id):02d}"
    return f"{collection_id}-{int(volume_id):01d}{int(paper_id):03d}"


def _text(el) -> str:
    """提取含行内标记的文本；<par> 视为段落分隔，折叠多余空白。"""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag == "par":
            parts.append("\n")
        parts.append(_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"[ \t]+", " ", "".join(parts)).strip()


def _first_text(parent, path: str) -> Optional[str]:
    el = parent.find(path)
    if el is None:
        return None
    text = _text(el)
    return text or None


class ACLAnthologySource(Source):
    name = "acl_anthology"
    command = "acl-anthology"
    summary = "ACL Anthology 会议论文（GitHub XML）"

    GITHUB_RAW = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=2, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        from lxml import etree

        collections = ctx.params.get("collections") or ["2024.acl"]
        now = datetime.now(timezone.utc)

        for col in collections:
            try:
                resp = await http_get(f"{self.GITHUB_RAW}/{col}.xml", ctx=ctx)
            except Exception as e:
                ctx.record_error(f"acl-anthology {col} 抓取失败：{type(e).__name__}: {e}")
                continue

            root = etree.fromstring(resp.content)
            col_id = root.get("id", col)

            for volume in root.findall("volume"):
                vol_id = volume.get("id", "")
                vmeta = volume.find("meta")
                if vmeta is None:
                    continue

                booktitle = _first_text(vmeta, "booktitle") or ""
                venues = [_text(v) for v in vmeta.findall("venue")]
                venue = venues[0] if venues else None
                vol_year = _first_text(vmeta, "year")
                vol_month = _first_text(vmeta, "month")

                for paper in volume.findall("paper"):
                    paper_id = paper.get("id", "")
                    anth_id = _build_anthology_id(col_id, vol_id, paper_id)

                    authors = []
                    for person in paper.findall("author"):
                        first = _first_text(person, "first")
                        last = _first_text(person, "last")
                        author = {
                            "name": " ".join(p for p in (first, last) if p),
                            "first": first,
                            "last": last,
                        }
                        if person.get("id"):
                            author["id"] = person.get("id")
                        authors.append(author)

                    attachments = []
                    for att in paper.findall("attachment"):
                        filename = (att.text or "").strip()
                        if filename:
                            attachments.append(
                                {
                                    "type": att.get("type") or "attachment",
                                    "name": filename,
                                    "url": f"{ANTHOLOGY_BASE}/attachments/{filename}",
                                }
                            )

                    external_urls = [(u.text or "").strip() for u in paper.findall("url")]
                    external_urls = [u for u in external_urls if u]

                    # 仅当 Anthology 实际托管 PDF（XML 含 <pdf>）时给出 pdf_url，避免 404
                    pdf_url = f"{ANTHOLOGY_BASE}/{anth_id}.pdf" if paper.find("pdf") is not None else None
                    videos = [v.get("href") for v in paper.findall("video") if v.get("href")]

                    data = {
                        "anthology_id": anth_id,
                        "title": _first_text(paper, "title"),
                        "authors": authors,
                        "year": vol_year,
                        "month": _first_text(paper, "month") or vol_month,
                        "venue": venue,
                        "venues": venues,
                        "booktitle": booktitle,
                        "pages": _first_text(paper, "pages"),
                        "doi": _first_text(paper, "doi"),
                        "language": _first_text(paper, "language"),
                        "abstract": _first_text(paper, "abstract"),
                        "url": f"{ANTHOLOGY_BASE}/{anth_id}/",
                        "pdf_url": pdf_url,
                        "external_urls": external_urls,
                        "attachments": attachments,
                        "videos": videos,
                    }
                    item_type = paper.get("type")
                    if item_type:
                        data["item_type"] = item_type

                    yield RawRecord(
                        source=self.name,
                        source_id=anth_id,
                        content_type="json",
                        fetched_at=now,
                        data=data,
                        metadata={"collection": col_id, "volume": vol_id, "venue": venue},
                    )
