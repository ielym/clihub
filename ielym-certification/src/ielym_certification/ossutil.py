"""ossutil 调用封装（凭证读取的传输层之一）。

只做一件事：把读/列操作翻译成 ossutil 命令行并执行，返回结构化结果。
凭证解析完全交给 ossutil 自身（配置文件 / 环境变量 / 命令行参数），本模块不接触密钥。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Sequence

OSSUTIL_ENV = "ALIYUN_OSS_OSSUTIL"


class OssutilNotFound(RuntimeError):
    """未找到 ossutil 可执行文件。"""


def find_ossutil() -> str:
    """定位 ossutil：环境变量优先，其次 PATH。"""
    override = os.environ.get(OSSUTIL_ENV)
    if override and os.path.exists(override):
        return override
    found = shutil.which("ossutil")
    if found:
        return found
    raise OssutilNotFound(
        "未找到 ossutil。请先安装 ossutil，或用环境变量 "
        f"{OSSUTIL_ENV} 指定其绝对路径。安装参考："
        "https://help.aliyun.com/zh/oss/install-ossutil2"
    )


@dataclass
class Result:
    """一次 ossutil 调用的结果。"""

    argv: list
    code: int
    stdout: str
    stderr: str
    elapsed_s: float
    endpoint: Optional[str] = None
    region: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(
    args: Sequence[str],
    *,
    endpoint: Optional[str] = None,
    region: Optional[str] = None,
    config_file: Optional[str] = None,
    profile: Optional[str] = None,
    quiet: bool = False,
    timeout: Optional[float] = None,
) -> Result:
    """执行一条 ossutil 子命令。

    quiet=True 时加 -q：抑制 ossutil 尾部的 "x.xxx(s) elapsed" 等提示，
    避免污染 cat 拿到的对象内容（不影响数据本身）。
    """
    argv = [find_ossutil(), *args]
    if endpoint:
        argv += ["-e", endpoint]
    if region:
        argv += ["--region", region]
    if config_file:
        argv += ["-c", config_file]
    if profile:
        argv += ["--profile", profile]
    if quiet:
        argv += ["-q"]

    started = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return Result(
        argv=argv,
        code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed_s=round(time.monotonic() - started, 3),
        endpoint=endpoint,
        region=region,
    )