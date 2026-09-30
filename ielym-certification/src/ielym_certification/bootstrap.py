"""引导凭证（bootstrap）：从飞书文档取回访问 OSS 凭证库的第一组 AK。

为什么需要它：
    ielym-certification 的凭证集中存放在 OSS，但读 OSS 本身又需要一组凭证，
    形成引导死循环。解法是引入独立的信任根——飞书登录态（lark-cli 扫码授权，
    与阿里云是两套权限体系）：

        飞书扫码登录（每台设备一次）
          → lark-cli 读取飞书文档中的引导凭证 JSON
          → 落盘为本工具专属的 0600 配置
          → ossutil 凭该配置读取 OSS 凭证库

其他 CLI/skill 只需调用 ielym-certification，完全不感知本模块的存在。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, Optional

from .providers.base import CertificationError

#: 引导凭证文档的默认地址（访问权由飞书侧权限控制，可用环境变量覆盖）
DEFAULT_FEISHU_DOC = "https://my.feishu.cn/docx/EQLFdZ1GWo9ttmxF1bhcQDhmnRg"

ENV_FEISHU_DOC = "IELYM_CERT_FEISHU_DOC"
ENV_LARK_BIN = "IELYM_CERT_LARK_CLI"

#: 文档中机器读取的 JSON 代码块
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
#: 兜底：第一个完整 JSON 对象
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class LarkCliNotFound(CertificationError):
    """未找到 lark-cli。"""


# ---------------------------------------------------------------- 路径

def config_dir() -> str:
    """引导配置目录：$XDG_CONFIG_HOME/ielym-certification 或 ~/.config/ielym-certification。"""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "ielym-certification")


def bootstrap_json_path() -> str:
    return os.path.join(config_dir(), "bootstrap.json")


def ossutil_config_path() -> str:
    """供 ossutil -c 使用的 ini 配置路径。"""
    return os.path.join(config_dir(), "ossutil.config")


def is_bootstrapped() -> bool:
    return os.path.exists(bootstrap_json_path()) and os.path.exists(
        ossutil_config_path()
    )


# ---------------------------------------------------------------- 飞书读取

def find_lark_cli() -> str:
    override = os.environ.get(ENV_LARK_BIN)
    if override and os.path.exists(override):
        return override
    found = shutil.which("lark-cli")
    if found:
        return found
    raise LarkCliNotFound(
        "未找到 lark-cli。ielym-certification 的引导凭证存放在飞书文档中，"
        "需要先安装 lark-cli 并完成飞书扫码登录（lark-cli auth login），"
        f"或用 ${ENV_LARK_BIN} 指定 lark-cli 的绝对路径。"
    )


def _extract_json(content: str) -> Dict[str, Any]:
    m = _JSON_BLOCK_RE.search(content) or _JSON_OBJECT_RE.search(content)
    if not m:
        raise CertificationError("引导文档中未找到凭证 JSON 代码块")
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        raise CertificationError(f"引导文档中的 JSON 解析失败：{exc}") from exc
    required = ("access_key_id", "access_key_secret", "region")
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise CertificationError(f"引导凭证缺少字段：{', '.join(missing)}")
    return data


def fetch_feishu_credential(doc_url: Optional[str] = None) -> Dict[str, Any]:
    """用 lark-cli 读取飞书文档并抽出凭证 JSON。"""
    url = doc_url or os.environ.get(ENV_FEISHU_DOC) or DEFAULT_FEISHU_DOC
    argv = [
        find_lark_cli(), "docs", "+fetch",
        "--doc", url,
        "--doc-format", "markdown",
        "--as", "user",
    ]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        tip = (proc.stderr or proc.stdout or "").strip()
        raise CertificationError(
            "读取飞书引导文档失败（通常是未安装/未登录 lark-cli，请先完成飞书扫码授权）："
            f"{tip or f'退出码 {proc.returncode}'}"
        )
    try:
        envelope = json.loads(proc.stdout)
        content = envelope["data"]["document"]["content"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CertificationError(f"lark-cli 返回内容无法解析：{exc}") from exc
    return _extract_json(content)


# ---------------------------------------------------------------- 落盘

def _write_0600(path: str, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _render_ossutil_config(cred: Dict[str, Any]) -> str:
    endpoint = (cred.get("endpoints") or {}).get("internal") or ""
    lines = [
        "[default]",
        f"accessKeyID={cred['access_key_id']}",
        f"accessKeySecret={cred['access_key_secret']}",
        f"region={cred['region']}",
    ]
    if endpoint:
        lines.append(f"endpoint={endpoint}")
    return "\n".join(lines) + "\n"


def write_bootstrap(cred: Dict[str, Any]) -> None:
    """把引导凭证写入本工具专属目录（目录 0700，文件 0600）。"""
    d = config_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    payload = dict(cred)
    payload["bootstrapped_at"] = datetime.now().astimezone().isoformat()
    _write_0600(bootstrap_json_path(), json.dumps(payload, ensure_ascii=False, indent=2))
    _write_0600(ossutil_config_path(), _render_ossutil_config(cred))


def load_bootstrap() -> Optional[Dict[str, Any]]:
    """读取已落盘的引导凭证；未引导时返回 None。"""
    path = bootstrap_json_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 对外动作

def bootstrap(*, force: bool = False, doc_url: Optional[str] = None) -> Dict[str, Any]:
    """执行一次引导：读飞书 → 落盘。已引导且未加 force 时拒绝覆盖。"""
    if is_bootstrapped() and not force:
        raise CertificationError(
            "本机已完成引导；确认要重新拉取并覆盖请加 --force"
        )
    cred = fetch_feishu_credential(doc_url)
    write_bootstrap(cred)
    return status()


def _mask(key: str) -> str:
    if len(key) <= 10:
        return "****"
    return f"{key[:6]}****{key[-4:]}"


def status() -> Dict[str, Any]:
    """引导状态（绝不输出 access_key_secret）。"""
    info: Dict[str, Any] = {
        "bootstrapped": is_bootstrapped(),
        "config_dir": config_dir(),
        "doc_url": os.environ.get(ENV_FEISHU_DOC) or DEFAULT_FEISHU_DOC,
    }
    cred = load_bootstrap() if is_bootstrapped() else None
    if cred:
        endpoints = cred.get("endpoints") or {}
        info.update(
            bucket=cred.get("bucket"),
            region=cred.get("region"),
            endpoint=endpoints.get("internal"),
            access_key_id=_mask(cred.get("access_key_id", "")),
            bootstrapped_at=cred.get("bootstrapped_at"),
        )
        try:
            info["updated_at"] = datetime.fromtimestamp(
                os.path.getmtime(bootstrap_json_path())
            ).astimezone().isoformat()
        except OSError:
            pass
    return info
