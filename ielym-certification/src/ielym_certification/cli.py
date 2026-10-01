"""ielym-certification 命令行入口。

命令形状：

    ielym-certification <provider> [provider 参数] [通用参数]

provider 由 registry 自动发现，新增权限无需改动本文件。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Type

from . import bootstrap
from . import __version__
from .ossutil import OssutilNotFound
from .providers.base import BaseProvider, CertificationError, NotFoundError
from .registry import discover

USAGE_HINT = """\
常用示例:
  ielym-certification bootstrap                                 首次引导（飞书扫码授权后拉取引导凭证）
  ielym-certification bootstrap --status                        查看引导状态
  ielym-certification providers                                 列出已支持的权限提供方
  ielym-certification aliyun-oss --bucket <bucket>              获取该 Bucket 的 OSS 凭证（直接输出内容）
  ielym-certification aliyun-oss --bucket <bucket> --json       输出带定位信息的 JSON 信封
  ielym-certification aliyun-oss --bucket <bucket> --out <file> 写入文件（权限 600）
  ielym-certification aliyun-oss --list                         列出已登记的凭证
  ielym-certification api-key --name <服务名>                   获取第三方服务的 API Key（JSON 原文）
  ielym-certification api-key --list                            列出已登记的第三方服务

扩展新权限: 在 providers/ 下新增一个 BaseProvider 子类即可，CLI 会自动加载。
"""


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true",
                   help="以 JSON 信封输出（含定位信息与内容）")
    p.add_argument("--out", default=None,
                   help="把凭证内容写入指定文件（权限 600）")
    p.add_argument("--list", action="store_true",
                   help="列出该 provider 下已登记的资源名")


def build_parser(providers: Dict[str, Type[BaseProvider]]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ielym-certification",
        description="统一的权限凭证获取 CLI（provider 可扩展）",
        epilog=USAGE_HINT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="provider", metavar="<provider>")

    for name, cls in sorted(providers.items()):
        p = sub.add_parser(name, help=cls.summary, description=cls.summary)
        cls().add_arguments(p)
        _add_common(p)

    sub.add_parser("providers", help="列出已支持的权限提供方")

    p = sub.add_parser(
        "bootstrap",
        help="一次性引导：经飞书登录态取回访问凭证库所需的引导凭证",
        description="经飞书文档（lark-cli 扫码授权）取回引导凭证并落盘为本工具专属配置；"
                    "每台设备只需执行一次，provider 细节见 skill 的 references。",
    )
    p.add_argument("--force", action="store_true", help="已引导时强制重新拉取并覆盖")
    p.add_argument("--status", action="store_true", help="只查看引导状态（不输出密钥）")
    p.add_argument("--doc-url", default=None,
                   help=f"引导文档地址；缺省读 ${bootstrap.ENV_FEISHU_DOC} 或内置地址")
    p.add_argument("--json", action="store_true", help="以 JSON 输出状态")
    return parser


def _print_providers(providers: Dict[str, Type[BaseProvider]]) -> None:
    if not providers:
        print("（暂无已注册的 provider）")
        return
    for name, cls in sorted(providers.items()):
        print(f"{name}\t{cls.summary}")


def _write_out(path: str, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"已写入 {path}（权限 600）", file=sys.stderr)


def _cmd_bootstrap(args) -> int:
    """引导：飞书登录态 → 本地引导凭证。"""
    if args.status:
        st = bootstrap.status()
    else:
        st = bootstrap.bootstrap(force=args.force, doc_url=args.doc_url)
        print("引导完成。", file=sys.stderr)

    if args.json:
        print(json.dumps(
            {"cli": "ielym-certification", "command": "bootstrap", **st},
            ensure_ascii=False, indent=2,
        ))
    else:
        if not st["bootstrapped"]:
            print("尚未引导：请先完成 lark-cli 飞书扫码登录，再执行 ielym-certification bootstrap")
            return 1
        print(f"已引导: bucket={st.get('bucket')} region={st.get('region')} "
              f"ak={st.get('access_key_id')}")
        print(f"配置目录: {st['config_dir']}")
    return 0 if st["bootstrapped"] else 1


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    providers = discover()
    parser = build_parser(providers)

    if not argv:
        parser.print_help()
        return 0

    if argv[0] == "providers":
        _print_providers(providers)
        return 0

    args = parser.parse_args(argv)
    if not args.provider:
        parser.print_help()
        return 0

    if args.provider == "bootstrap":
        return _cmd_bootstrap(args)

    provider = providers[args.provider]()

    try:
        # --list 不定位具体凭证，需在 target() 之前处理（部分 provider 无默认 name）
        if args.list:
            names = provider.list_names(args)
            if args.json:
                print(json.dumps({
                    "cli": "ielym-certification",
                    "provider": args.provider,
                    "command": "list",
                    "ok": True,
                    "count": len(names),
                    "names": names,
                }, ensure_ascii=False, indent=2))
            else:
                for n in names:
                    print(n)
            return 0

        target = provider.target(args)
        text = provider.fetch(args)
        if args.out:
            _write_out(args.out, text)
        if args.json:
            print(json.dumps({
                "cli": "ielym-certification",
                "provider": args.provider,
                "command": "get",
                "ok": True,
                **target,
                "content": text,
            }, ensure_ascii=False, indent=2))
        elif not args.out:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
        return 0

    except NotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    except (CertificationError, OssutilNotFound) as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130