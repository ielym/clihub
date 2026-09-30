"""数据源集合。"""
from __future__ import annotations

from ..base import Source
from .acl_anthology import ACLAnthologySource
from .arxiv import ArxivSource
from .artificial_analysis import ArtificialAnalysisSource
from .cvf import CVFSource
from .dblp import DBLPSource
from .github_trending import GithubTrendingSource
from .huggingface_papers import HuggingFacePapersSource
from .openreview import OpenReviewSource
from .openrouter import OpenRouterSource
from .pmlr import PMLRSource

# 指令顺序即列出顺序
ALL_SOURCES: list[Source] = [
    ArxivSource(),
    GithubTrendingSource(),
    OpenReviewSource(),
    HuggingFacePapersSource(),
    ArtificialAnalysisSource(),
    OpenRouterSource(),
    ACLAnthologySource(),
    PMLRSource(),
    CVFSource(),
    DBLPSource(),
]

__all__ = ["ALL_SOURCES"]