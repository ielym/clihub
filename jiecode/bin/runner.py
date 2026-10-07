#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jiecode —— 通用接码 CLI。

平台以 provider 方式接入。当前内置 d1jiema。

凭证解析：
1. 各 provider 的专用环境变量（例如 D1_TOKEN / D1_API_BASE）；
2. 全局配置文件 providers.<provider> 段；
3. 配置路径默认 ~/.config/jiecode/config.json，可用 --config 或 $JIE_CODE_CONFIG 覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".config" / "jiecode" / "config.json"
PROVIDERS: dict[str, type["BaseProvider"]] = {}


def register_provider(cls: type["BaseProvider"]) -> type["BaseProvider"]:
    PROVIDERS[cls.name] = cls
    return cls


class BaseProvider:
    name = ""

    def load_credentials(self, provider_config: dict) -> dict:
        raise NotImplementedError

    def status(self, creds: dict) -> str:
        raise NotImplementedError

    def get_phone(self, creds: dict, keyword: str, phone: str, province: str, card_type: str) -> str:
        raise NotImplementedError

    def get_msg(self, creds: dict, phone: str, keyword: str) -> str:
        raise NotImplementedError

    def history(self, creds: dict) -> str:
        raise NotImplementedError


@register_provider
class D1Provider(BaseProvider):
    """D1 接码（易码）provider。"""

    name = "d1jiema"
    default_api_base = "https://api.d1jiema.com/zc/data.php"

    def load_credentials(self, provider_config: dict) -> dict:
        token = os.environ.get("D1_TOKEN") or provider_config.get("api_token")
        api_base = os.environ.get("D1_API_BASE") or provider_config.get("api_base") or self.default_api_base
        if not token:
            raise SystemExit(
                f"错误：{self.name} 缺少 api_token。请设置 D1_TOKEN 或配置 providers.d1jiema.api_token。"
            )
        return {
            "account": os.environ.get("D1_ACCOUNT") or provider_config.get("account", ""),
            "api_token": token,
            "api_base": api_base,
        }

    def _call(self, creds: dict, code: str, params: dict[str, str]) -> str:
        query: dict[str, str] = {"code": code, "token": creds["api_token"]}
        query.update({k: v for k, v in params.items() if v not in (None, "")})
        url = creds["api_base"] + "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, headers={"User-Agent": "jiecode/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", "replace")

    def status(self, creds: dict) -> str:
        return self._call(creds, "leftAmount", {})

    def get_phone(self, creds: dict, keyword: str, phone: str, province: str, card_type: str) -> str:
        return self._call(
            creds,
            "getPhone",
            {
                "keyWord": keyword,
                "phone": phone,
                "province": province,
                "cardType": card_type or "全部",
            },
        )

    def get_msg(self, creds: dict, phone: str, keyword: str) -> str:
        return self._call(creds, "getMsg", {"phone": phone, "keyWord": keyword})

    def history(self, creds: dict) -> str:
        return self._call(creds, "queryUsed", {})


def load_global_config(args: argparse.Namespace) -> tuple[dict, Path]:
    path = Path(args.config or os.environ.get("JIE_CODE_CONFIG") or DEFAULT_CONFIG)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8")), path
    return {}, path


def select_provider(args: argparse.Namespace, config: dict) -> str:
    name = args.provider or os.environ.get("JIE_CODE_PROVIDER") or config.get("default_provider")
    if not name:
        known = ", ".join(sorted(PROVIDERS))
        raise SystemExit(f"错误：未指定 provider。可用：{known}")
    return name


def get_provider(name: str) -> BaseProvider:
    cls = PROVIDERS.get(name)
    if cls is None:
        known = ", ".join(sorted(PROVIDERS))
        raise SystemExit(f"错误：未知 provider：{name}。可用：{known}")
    return cls()


def emit(command: str, provider: str, result: str, json_mode: bool) -> int:
    ok = not result.startswith("ERROR:")
    if json_mode:
        print(json.dumps({"ok": ok, "command": command, "provider": provider, "data": result}, ensure_ascii=False))
    else:
        print(result)
    return 0 if ok else 1


def cmd_providers(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    result = "\n".join(sorted(PROVIDERS))
    return emit("providers", "", result, args.json)


def cmd_status(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    name = select_provider(args, config)
    provider = get_provider(name)
    creds = provider.load_credentials(config.get("providers", {}).get(name, {}))
    return emit("status", name, provider.status(creds), args.json)


def cmd_get_phone(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    name = select_provider(args, config)
    provider = get_provider(name)
    creds = provider.load_credentials(config.get("providers", {}).get(name, {}))
    result = provider.get_phone(
        creds,
        keyword=args.keyword,
        phone=args.phone,
        province=args.province,
        card_type=args.card_type,
    )
    return emit("get-phone", name, result, args.json)


def cmd_get_msg(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    name = select_provider(args, config)
    provider = get_provider(name)
    creds = provider.load_credentials(config.get("providers", {}).get(name, {}))
    result = provider.get_msg(creds, phone=args.phone, keyword=args.keyword)
    return emit("get-msg", name, result, args.json)


def cmd_history(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    name = select_provider(args, config)
    provider = get_provider(name)
    creds = provider.load_credentials(config.get("providers", {}).get(name, {}))
    return emit("history", name, provider.history(creds), args.json)


def cmd_credential_path(args: argparse.Namespace, config: dict, config_path: Path) -> int:
    print(str(config_path))
    return 0


def _add_sub(sub, name: str) -> argparse.ArgumentParser:
    p = sub.add_parser(name)
    p.add_argument("--json", action="store_true", help="输出 JSON 信封")
    return p


def main() -> int:
    parser = argparse.ArgumentParser(prog="jiecode", description="通用接码 CLI。")
    parser.add_argument("--provider", default=None, help="平台 provider；缺省用 $JIE_CODE_PROVIDER 或配置 default_provider")
    parser.add_argument("--config", default=None, help="全局配置文件，缺省 $JIE_CODE_CONFIG 或 ~/.config/jiecode/config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    _add_sub(sub, "providers").set_defaults(func=cmd_providers)

    p = _add_sub(sub, "status")
    p.set_defaults(func=cmd_status)

    p = _add_sub(sub, "get-phone")
    p.add_argument("--keyword", default="", help="短信关键词，例如平台名")
    p.add_argument("--phone", default="", help="指定号码；不填则随机取号")
    p.add_argument("--province", default="", help="归属地省份（provider 支持时生效）")
    p.add_argument("--card-type", default="", help="卡类型（provider 支持时生效）")
    p.set_defaults(func=cmd_get_phone)

    p = _add_sub(sub, "get-msg")
    p.add_argument("--phone", required=True, help="已取到的手机号")
    p.add_argument("--keyword", required=True, help="短信关键词")
    p.set_defaults(func=cmd_get_msg)

    _add_sub(sub, "history").set_defaults(func=cmd_history)
    _add_sub(sub, "credential-path").set_defaults(func=cmd_credential_path)

    args = parser.parse_args()
    config, config_path = load_global_config(args)
    return args.func(args, config, config_path)


if __name__ == "__main__":
    sys.exit(main())