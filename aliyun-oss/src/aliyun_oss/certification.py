"""凭证统一入口：aliyun-oss 的所有凭证只来自 ielym-certification。

本模块是 aliyun-oss 唯一的认证来源：
  - 不读 ossutil 配置文件，不收手工 AK/SK；
  - 凭证的引导过程（飞书登录态等）完全封装在 ielym-certification 内部，
    本模块与其调用方一律不感知。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

#: ielym-certification 可执行文件覆盖路径
BIN_ENV = "ALIYUN_OSS_CERTIFICATION_BIN"

_OSS_PATH_RE = re.compile(r"oss://([^/\s?#]+)")


class CertificationUnavailable(RuntimeError):
    """无法从 ielym-certification 取得凭证。"""


@dataclass
class Credential:
    """一次取回的 OSS 凭证（同进程内可缓存复用）。"""

    access_key_id: str
    access_key_secret: str
    region: Optional[str]
    internal_endpoint: Optional[str]
    public_endpoint: Optional[str]
    bucket: Optional[str]

    @property
    def endpoint(self) -> Optional[str]:
        return self.internal_endpoint


def find_certification_bin() -> str:
    override = os.environ.get(BIN_ENV)
    if override and os.path.exists(override):
        return override
    found = shutil.which("ielym-certification")
    if found:
        return found
    raise CertificationUnavailable(
        "未找到 ielym-certification。aliyun-oss 的凭证统一由它提供，"
        "请先安装 ielym-certification 并按其说明完成一次性引导。"
    )


def bucket_from_argv(argv: List[str]) -> Optional[str]:
    """从 ossutil 参数里的 oss:// 路径提取 bucket（取第一个即可定位凭证）。"""
    for token in argv:
        m = _OSS_PATH_RE.search(token)
        if m:
            return m.group(1)
    return None


def _run_certification(args: List[str]) -> Dict[str, Any]:
    argv = [find_certification_bin(), *args]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise CertificationUnavailable(detail or f"ielym-certification 退出码 {proc.returncode}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CertificationUnavailable(f"ielym-certification 输出无法解析：{exc}") from exc


def get_credential(bucket: Optional[str] = None) -> Credential:
    """向 ielym-certification 取回指定 Bucket 的凭证。

    bucket 为 None 时，由 ielym-certification 返回其凭证库默认 Bucket 的凭证。
    """
    args = ["aliyun-oss", "--json"]
    if bucket:
        args[1:1] = ["--bucket", bucket]
    envelope = _run_certification(args)
    if not envelope.get("ok"):
        raise CertificationUnavailable(
            f"ielym-certification 返回失败：{envelope.get('error') or envelope}"
        )
    try:
        data = json.loads(envelope["content"])
    except (KeyError, json.JSONDecodeError, TypeError) as exc:
        raise CertificationUnavailable(f"凭证内容无法解析：{exc}") from exc

    endpoints = data.get("endpoints") or {}
    return Credential(
        access_key_id=data["access_key_id"],
        access_key_secret=data["access_key_secret"],
        region=data.get("region"),
        internal_endpoint=endpoints.get("internal"),
        public_endpoint=endpoints.get("public"),
        bucket=data.get("bucket"),
    )


def bootstrap_status() -> Dict[str, Any]:
    """ielym-certification 的引导状态（供 info 展示，不含密钥明文）。"""
    argv = [find_certification_bin(), "bootstrap", "--status", "--json"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"bootstrapped": False, "detail": (proc.stderr or proc.stdout).strip()}
