"""ArtificialAnalysis 凭据入口：API Key 只来自 ielym-certification 的 api-key provider（OSS 凭证库）。

凭证库存放约定：

    oss://<store-bucket>/certification/api-key/<service>/<service>.json

本模块只按服务名调用 `ielym-certification api-key` 并从返回的 JSON 原文中取字段，
不感知引导过程（飞书登录态等完全封装在 ielym-certification 内）。
"""
from __future__ import annotations

import json
import shutil
import subprocess

SERVICE = "artificial-analysis"
FIELD = "AA_API_KEY"


class CredentialError(RuntimeError):
    """无法从凭证库取得凭据（含原因）。"""


class CredentialNotFound(CredentialError):
    """凭证库中未登记该服务的凭据。"""


def find_certification_bin() -> str:
    found = shutil.which("ielym-certification")
    if found:
        return found
    raise CredentialError(
        "未找到 ielym-certification。artificial-analysis 的凭据统一由它从 OSS 凭证库提供，"
        "请先安装 ielym-certification 并按其说明完成一次性引导。"
    )


def get_credential() -> str:
    """取回 ArtificialAnalysis API Key。

    服务未登记抛 CredentialNotFound；其它失败（未引导 / 网络 / 输出无法解析 / 缺字段）
    抛 CredentialError，消息带原因。
    """
    argv = [find_certification_bin(), "api-key", "--name", SERVICE, "--json"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except OSError as e:
        raise CredentialError(f"执行 ielym-certification 失败：{e}") from e

    detail = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode == 2:
        raise CredentialNotFound(detail or f"凭证库中未登记服务 {SERVICE} 的凭据")
    if proc.returncode != 0:
        raise CredentialError(detail or f"ielym-certification 退出码 {proc.returncode}")

    try:
        envelope = json.loads(proc.stdout)
        content = json.loads(envelope["content"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise CredentialError(f"ielym-certification 返回无法解析：{type(e).__name__}: {e}") from e

    value = content.get(FIELD)
    if not value:
        raise CredentialError(f"凭据 {envelope.get('oss_path')} 的 JSON 中缺少非空字段 {FIELD}")
    return value