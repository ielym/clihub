"""ip-tunnel 凭据入口：隧道账号只来自 ielym-certification 的 api-key provider（OSS 凭证库）。

凭证库存放约定：

    oss://<store-bucket>/certification/api-key/<service>/<service>.json

本模块只按服务名调用 `ielym-certification api-key` 并从返回的 JSON 原文中取字段，
不感知引导过程（飞书登录态等完全封装在 ielym-certification 内）。

凭证 JSON 字段：
    tunnel           隧道地址 host:port
    username         隧道用户名
    password         隧道密码
    rate_limit_per_sec  购买并发数（次/秒），默认 5
    bandwidth_mbps   带宽峰值（Mbps），默认 5
    ip_rotation      换 IP 模式，默认 "per_request"
    bandwidth_overage  超带宽机制，默认 "request_queued"
"""
from __future__ import annotations

import json
import shutil
import subprocess

SERVICE = "ip-tunnel"

DEFAULTS = {
    "rate_limit_per_sec": 5,
    "bandwidth_mbps": 5,
    "ip_rotation": "per_request",
    "bandwidth_overage": "request_queued",
}


class CredentialError(RuntimeError):
    """无法从凭证库取得凭据（含原因）。"""


class CredentialNotFound(CredentialError):
    """凭证库中未登记该服务的凭据。"""


def _mask(value: str) -> str:
    s = str(value)
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "****" + s[-2:]


def find_certification_bin() -> str:
    found = shutil.which("ielym-certification")
    if found:
        return found
    raise CredentialError(
        "未找到 ielym-certification。ip-tunnel 的隧道账号统一由它从 OSS 凭证库提供，"
        "请先安装 ielym-certification 并按其说明完成一次性引导。"
    )


def get_credential() -> dict:
    """取回隧道代理凭证（dict）。

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

    for field in ("tunnel", "username", "password"):
        if not content.get(field):
            raise CredentialError(
                f"凭据 {envelope.get('oss_path')} 的 JSON 中缺少非空字段 {field}"
            )

    merged = {**DEFAULTS, **content}
    merged["service"] = SERVICE
    merged["oss_path"] = envelope.get("oss_path")
    try:
        merged["rate_limit_per_sec"] = int(merged["rate_limit_per_sec"])
    except (TypeError, ValueError):
        merged["rate_limit_per_sec"] = DEFAULTS["rate_limit_per_sec"]
    return merged


def masked_summary(cred: dict) -> dict:
    """返回不泄露密码的摘要（用于人类可读输出 / --json 不带密码时）。"""
    return {
        "service": cred["service"],
        "tunnel": cred["tunnel"],
        "username": cred["username"],
        "password": _mask(cred["password"]),
        "rate_limit_per_sec": cred["rate_limit_per_sec"],
        "bandwidth_mbps": cred["bandwidth_mbps"],
        "ip_rotation": cred["ip_rotation"],
        "bandwidth_overage": cred["bandwidth_overage"],
        "oss_path": cred["oss_path"],
    }