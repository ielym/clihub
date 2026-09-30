"""provider 注册表 —— 自动发现 providers 包下的所有权限提供方。

新增 provider 不需要改本文件：在 providers/ 下加一个 BaseProvider 子类即可。
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Type

from .providers.base import BaseProvider

# 不作为 provider 载入的模块
_SKIP = {"base"}


def discover() -> Dict[str, Type[BaseProvider]]:
    """返回 {provider 名: 实现类}。"""
    from . import providers as pkg

    found: Dict[str, Type[BaseProvider]] = {}
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_") or info.name in _SKIP:
            continue
        module = importlib.import_module(f"{pkg.__name__}.{info.name}")
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseProvider)
                and obj is not BaseProvider
                and getattr(obj, "name", "")
            ):
                found[obj.name] = obj
    return found