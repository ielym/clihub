"""权限提供方基类。

一个 provider 负责一类权限的「定位 + 取回」：
  - add_arguments()  声明它自己的命令行参数
  - target()         说明凭证在哪里（用于输出与错误提示）
  - fetch()          取回凭证内容（文本）
  - list_names()     可选：列出该 provider 下已登记的资源名
"""
from __future__ import annotations

import abc
import argparse
from typing import Any, Dict, List


class CertificationError(RuntimeError):
    """获取凭证过程中的一般性错误。"""


class NotFoundError(CertificationError):
    """目标凭证不存在。"""


class BaseProvider(abc.ABC):
    """所有权限提供方的基类。"""

    #: provider 名，即命令行第一个参数，如 "aliyun-oss"
    name: str = ""
    #: 一句话说明，出现在 --help 与 `providers` 列表中
    summary: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """声明该 provider 特有的命令行参数。"""

    def target(self, args: argparse.Namespace) -> Dict[str, Any]:
        """返回凭证的定位信息（结构化），用于输出与错误提示。"""
        return {}

    @abc.abstractmethod
    def fetch(self, args: argparse.Namespace) -> str:
        """取回凭证内容（文本）。不存在时抛 NotFoundError。"""

    def list_names(self, args: argparse.Namespace) -> List[str]:
        """列出该 provider 下已登记的资源名。"""
        raise CertificationError(f"provider {self.name} 暂不支持列出凭证")