"""ossutil 调用封装。

本模块只做一件事：把高层操作翻译成 ossutil 命令行并执行，返回结构化结果。
凭证由 certification 模块（ielym-certification）统一取回，通过子进程环境变量
一次性注入，本模块不读配置文件、不接触任何其他凭证来源。
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
        "https://help.aliyun.com/zh/oss/developer-reference/ossutil-overview/"
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
    access_key_id: Optional[str] = None,
    access_key_secret: Optional[str] = None,
    output_format: Optional[str] = None,
    force: bool = False,
    timeout: Optional[float] = None,
) -> Result:
    """执行一条 ossutil 子命令。

    凭证（access_key_id/secret）由 ielym-certification 取回后通过子进程环境变量
    注入，不写入 argv、不落盘；本函数不再读取任何 ossutil 配置文件。
    """
    argv = [find_ossutil(), *args]
    if endpoint:
        argv += ["-e", endpoint]
    if region:
        argv += ["--region", region]
    if output_format:
        argv += ["--output-format", output_format]
    if force:
        argv += ["-f"]

    env = None
    if access_key_id and access_key_secret:
        # 凭证只来自我方注入：-c 指向空设备，彻底屏蔽 ossutil 配置文件；
        # AK/SK 经环境变量传入，不进 argv、不落盘
        argv += ["-c", os.devnull]
        env = {
            **os.environ,
            "OSS_ACCESS_KEY_ID": access_key_id,
            "OSS_ACCESS_KEY_SECRET": access_key_secret,
        }

    started = time.monotonic()
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    return Result(
        argv=argv,
        code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed_s=round(time.monotonic() - started, 3),
        endpoint=endpoint,
        region=region,
    )