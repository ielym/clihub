"""DBLP 数据源。

DBLP 实时接口受 Anubis 反爬保护，采用 XML dump 解析（CC0）。
三种模式：
  - sample：内置样本，用于连通性自检
  - local：解析本地 XML / XML.GZ 文件
  - download：下载最新 dump 后解析
"""
from __future__ import annotations

import gzip
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from ..base import Source
from ..context import FetchContext, RateLimitConfig, http_get
from ..raw import RawRecord

MOCK_DBLP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dblp>
  <article key="journals/corr/abs-1706-03762" mdate="2024-01-01">
    <author>Martin Abadi</author>
    <author>Ashish Agarwal</author>
    <title>Deep Learning with Differential Privacy.</title>
    <pages>1-10</pages>
    <year>2016</year>
    <booktitle>Proceedings of the 2016 ACM SIGSAC Conference on Computer and Communications Security</booktitle>
    <ee>https://arxiv.org/abs/1706.03762</ee>
    <type>article</type>
  </article>
  <inproceedings key="conf/icml/AbadiZ16" mdate="2016-06-23">
    <author>Martin Abadi</author>
    <author>David G. Andersen</author>
    <title>Learning to Protect Communications with Adversarial Neural Cryptography.</title>
    <year>2016</year>
    <booktitle>ICML</booktitle>
    <ee>http://proceedings.mlr.press/v48/abadi16.html</ee>
    <type>inproceedings</type>
  </inproceedings>
</dblp>
"""

RECORD_TAGS = (
    "article", "inproceedings", "proceedings", "book",
    "incollection", "phdthesis", "mastersthesis", "www", "data",
)


class DBLPSource(Source):
    name = "dblp"
    command = "dblp"
    summary = "DBLP 文献库（XML dump）"

    @property
    def rate_limit(self) -> RateLimitConfig:
        return RateLimitConfig(retry_times=3, retry_backoff=1.0)

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[RawRecord]:
        mode = ctx.params.get("mode", "sample")
        now = datetime.now(timezone.utc)

        if mode == "local" and not ctx.params.get("dump"):
            ctx.record_error("dblp mode=local 需要 --dump 指定本地 XML / .xml.gz 路径")
            return

        if mode == "local" and ctx.params.get("dump"):
            content = self._read_dump(ctx.params["dump"])
            for record in self._parse_xml(content, ctx):
                record.fetched_at = now
                yield record
            return

        if mode == "download":
            dump_url = await self._latest_dump_url(ctx)
            if dump_url:
                resp = await http_get(dump_url, ctx=ctx)
                content = resp.content
                if dump_url.endswith(".gz"):
                    content = gzip.decompress(content)
                for record in self._parse_xml(content.decode("utf-8", errors="ignore"), ctx):
                    record.fetched_at = now
                    yield record
            return

        # 默认 sample
        for record in self._parse_xml(MOCK_DBLP_XML, ctx):
            record.fetched_at = now
            yield record

    async def _latest_dump_url(self, ctx: FetchContext) -> Optional[str]:
        try:
            resp = await http_get("https://dblp.org/xml/release/", ctx=ctx)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a"):
                href = a.get("href", "")
                if href.endswith(".xml.gz"):
                    return "https://dblp.org/xml/release/" + href
            ctx.record_error("dblp 未在 release 页面找到 .xml.gz dump 链接")
        except Exception as e:
            ctx.record_error(f"dblp dump 链接发现失败：{type(e).__name__}: {e}")
        return None

    def _read_dump(self, path: str) -> str:
        if path.endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                return f.read()
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _parse_xml(self, xml_content: str, ctx: Optional[FetchContext] = None) -> list[RawRecord]:
        from lxml import etree

        records: list[RawRecord] = []
        try:
            root = etree.fromstring(xml_content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            if ctx is not None:
                ctx.record_error(f"dblp XML 解析失败：{e}")
            return records

        for elem in root:
            tag = elem.tag
            if tag not in RECORD_TAGS:
                continue
            key = elem.get("key")
            if not key:
                continue
            records.append(RawRecord(
                source=self.name,
                source_id=key,
                content_type="xml",
                fetched_at=datetime.now(timezone.utc),
                data=etree.tostring(elem, encoding="unicode"),
                metadata={"type": tag},
            ))
        return records