"""aliyun-oss 命令行入口。

子命令围绕「上传 / 下载 / 管理 OSS 文件」组织，统一交给 ossutil 执行。
默认透传 ossutil 的可读输出；加 --json 时输出结构化信封，便于程序化消费。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from functools import lru_cache
from typing import Optional

from . import __version__, certification
from .certification import CertificationUnavailable, Credential
from .ossutil import OssutilNotFound, Result, find_ossutil, run

# 缺省 Bucket 可用环境变量提供，避免每次输入；凭证/endpoint/region 均来自
# ielym-certification，不在本 CLI 配置
DEFAULT_BUCKET_ENV = "ALIYUN_OSS_BUCKET"

USAGE_HINT = """\
常用示例:
  aliyun-oss info                                            查看当前配置与环境
  aliyun-oss buckets                                         列出所有 Bucket
  aliyun-oss ls oss://my-bucket/data/                        列出对象
  aliyun-oss upload ./report.pdf oss://my-bucket/reports/     上传文件
  aliyun-oss upload ./dataset/ oss://my-bucket/dataset/      上传整个目录（自动递归）
  aliyun-oss download oss://my-bucket/reports/report.pdf ./  下载文件
  aliyun-oss rm oss://my-bucket/tmp/a.txt                    删除对象
  aliyun-oss du oss://my-bucket/                             统计用量
  aliyun-oss presign oss://my-bucket/a.png --timeout 3600    生成签名 URL

省钱提示: 同地域 ECS 上把 endpoint 设为内网域名（如
  oss-cn-<region>-internal.aliyuncs.com）上传下载均免流量费。
"""


def _add_global(p: argparse.ArgumentParser) -> None:
    p.add_argument("-e", "--endpoint", default=None,
                   help="覆盖 OSS 访问域名（默认用 ielym-certification 返回的内网域名；"
                        "生成公网链接时显式指定外网域名）")
    p.add_argument("--region", default=None,
                   help="覆盖地域 ID；默认取 ielym-certification 返回的地域")
    p.add_argument("--json", action="store_true", help="以 JSON 信封输出结果")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aliyun-oss",
        description="阿里云 OSS 常用操作 CLI（底层调用 ossutil）",
        epilog=USAGE_HINT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("buckets", help="列出当前账号下所有 Bucket")
    _add_global(p)

    p = sub.add_parser("ls", aliases=["list"], help="列出 Bucket 或对象")
    _add_global(p)
    p.add_argument("path", nargs="?", default=None, help="oss://bucket[/prefix]，省略则列出所有 Bucket")
    p.add_argument("-r", "--recursive", action="store_true", help="递归列出")

    p = sub.add_parser("upload", aliases=["up", "put"], help="上传本地文件/目录到 OSS")
    _add_global(p)
    p.add_argument("source", help="本地文件或目录路径")
    p.add_argument("target", nargs="?", default=None,
                   help=f"oss://bucket[/key]；缺省用 ${DEFAULT_BUCKET_ENV} + 文件名")
    p.add_argument("-r", "--recursive", action="store_true", help="递归（source 为目录时自动开启）")

    p = sub.add_parser("download", aliases=["down", "get"], help="下载 OSS 对象到本地")
    _add_global(p)
    p.add_argument("source", help="oss://bucket/key")
    p.add_argument("target", nargs="?", default=None, help="本地路径；缺省为当前目录同名文件")
    p.add_argument("-r", "--recursive", action="store_true", help="递归下载目录")

    p = sub.add_parser("cp", help="通用拷贝（自动识别方向，支持 OSS 之间）")
    _add_global(p)
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("-r", "--recursive", action="store_true")

    p = sub.add_parser("sync", help="增量同步目录（本地 -> OSS、OSS -> OSS）")
    _add_global(p)
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("--delete", action="store_true", help="删除目标端多余文件（谨慎）")

    p = sub.add_parser("rm", aliases=["delete", "del"], help="删除对象")
    _add_global(p)
    p.add_argument("path", help="oss://bucket/key")
    p.add_argument("-r", "--recursive", action="store_true", help="递归删除目录")

    p = sub.add_parser("du", help="统计 Bucket 或目录的存储用量")
    _add_global(p)
    p.add_argument("path", nargs="?", default=None, help="oss://bucket[/prefix]")

    p = sub.add_parser("presign", aliases=["sign", "url"], help="生成对象的签名 URL")
    _add_global(p)
    p.add_argument("path", help="oss://bucket/key")
    p.add_argument("--timeout", type=int, default=None, help="有效期（秒），如 3600")
    p.add_argument("--expires", default=None, help="有效期时长，如 15m/1h/1d（优先于 --timeout）")

    p = sub.add_parser("stat", help="显示对象的元数据（大小、ETag、修改时间等）")
    _add_global(p)
    p.add_argument("path", help="oss://bucket/key")

    p = sub.add_parser("exists", aliases=["check"], help="判断对象是否存在（存在退出 0，不存在退出 1）")
    _add_global(p)
    p.add_argument("path", help="oss://bucket/key")

    p = sub.add_parser("info", help="显示当前环境与配置（不打印密钥）")
    _add_global(p)

    return parser


# ---------------------------------------------------------------- 辅助

@lru_cache(maxsize=None)
def _credential(bucket: Optional[str]) -> Credential:
    """同一次命令执行内按 bucket 缓存凭证（避免重复取回）。"""
    return certification.get_credential(bucket)


def _run(args, oss_args, *, force=False) -> Result:
    bucket = certification.bucket_from_argv(oss_args)
    cred = _credential(bucket)
    return run(
        oss_args,
        endpoint=args.endpoint or cred.endpoint,
        region=args.region or cred.region,
        access_key_id=cred.access_key_id,
        access_key_secret=cred.access_key_secret,
        output_format="json" if args.json else None,
        force=force,
    )


def _default_bucket_target(src: str) -> str:
    bucket = os.environ.get(DEFAULT_BUCKET_ENV)
    if not bucket:
        raise SystemExit(
            f"错误：未给出 target，且未设置 ${DEFAULT_BUCKET_ENV}（bucket 名）。"
        )
    return f"oss://{bucket}/{os.path.basename(os.path.normpath(src))}"


# ---------------------------------------------------------------- 子命令

def _cmd_buckets(args) -> Result:
    return _run(args, ["ls"])


def _cmd_ls(args) -> Result:
    oss_args = ["ls"]
    if args.path:
        oss_args.append(args.path)
    if args.recursive:
        oss_args.append("-r")
    return _run(args, oss_args)


def _cmd_upload(args) -> Result:
    src = args.source
    target = args.target or _default_bucket_target(src)
    recursive = args.recursive or os.path.isdir(src)
    oss_args = ["cp", src, target]
    if recursive:
        oss_args.append("-r")
    return _run(args, oss_args, force=True)


def _cmd_download(args) -> Result:
    src = args.source
    target = args.target or os.path.basename(src.rstrip("/")) or "."
    oss_args = ["cp", src, target]
    if args.recursive:
        oss_args.append("-r")
    return _run(args, oss_args, force=True)


def _cmd_cp(args) -> Result:
    oss_args = ["cp", args.source, args.target]
    if args.recursive:
        oss_args.append("-r")
    return _run(args, oss_args, force=True)


def _cmd_sync(args) -> Result:
    oss_args = ["sync", args.source, args.target]
    if args.delete:
        oss_args.append("--delete")
    return _run(args, oss_args, force=True)


def _cmd_rm(args) -> Result:
    oss_args = ["rm", args.path]
    if args.recursive:
        oss_args.append("-r")
    return _run(args, oss_args, force=True)


def _cmd_du(args) -> Result:
    oss_args = ["du"]
    if args.path:
        oss_args.append(args.path)
    return _run(args, oss_args)


def _cmd_presign(args) -> Result:
    oss_args = ["presign", args.path]
    if args.expires:
        oss_args += ["--expires-duration", args.expires]
    elif args.timeout:
        oss_args += ["--expires-duration", f"{args.timeout}s"]
    return _run(args, oss_args)


def _cmd_stat(args) -> Result:
    return _run(args, ["stat", args.path])


def _cmd_exists(args) -> int:
    """判断对象是否存在。存在返回 0，不存在返回 1。"""
    res = _run(args, ["stat", args.path])
    exists = res.ok
    if args.json:
        print(json.dumps(
            {
                "cli": "aliyun-oss",
                "command": "exists",
                "path": args.path,
                "exists": exists,
                "exit_code": 0 if exists else 1,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print("true" if exists else "false")
    return 0 if exists else 1


def _cmd_info(args) -> None:
    """打印当前环境与凭证来源状态（绝不输出 AccessKey Secret）。"""
    info = {
        "version": __version__,
        "ossutil": None,
        "default_bucket": os.environ.get(DEFAULT_BUCKET_ENV),
        "credential_source": "ielym-certification",
        "certification_cli": None,
        "bootstrapped": False,
    }
    try:
        info["ossutil"] = find_ossutil()
    except OssutilNotFound as exc:
        info["ossutil"] = f"未找到：{exc}"

    try:
        info["certification_cli"] = certification.find_certification_bin()
        st = certification.bootstrap_status()
        info["bootstrapped"] = bool(st.get("bootstrapped"))
        if st.get("bucket"):
            info["bucket"] = st["bucket"]
        if st.get("region"):
            info["region"] = st["region"]
        if st.get("endpoint"):
            info["endpoint"] = st["endpoint"]
        if st.get("access_key_id"):
            info["access_key_id"] = st["access_key_id"]
    except CertificationUnavailable as exc:
        info["certification_cli"] = f"未找到：{exc}"

    print(json.dumps(info, ensure_ascii=False, indent=2))


_HANDLERS = {
    "buckets": _cmd_buckets,
    "ls": _cmd_ls,
    "list": _cmd_ls,
    "upload": _cmd_upload,
    "up": _cmd_upload,
    "put": _cmd_upload,
    "download": _cmd_download,
    "down": _cmd_download,
    "get": _cmd_download,
    "cp": _cmd_cp,
    "sync": _cmd_sync,
    "rm": _cmd_rm,
    "delete": _cmd_rm,
    "del": _cmd_rm,
    "du": _cmd_du,
    "presign": _cmd_presign,
    "sign": _cmd_presign,
    "url": _cmd_presign,
    "stat": _cmd_stat,
}


def _emit(args, result: Result) -> None:
    if args.json:
        envelope = {
            "cli": "aliyun-oss",
            "command": args.command,
            "ok": result.ok,
            "exit_code": result.code,
            "elapsed_s": result.elapsed_s,
            "endpoint": result.endpoint,
            "region": result.region,
            "command_line": result.argv,
        }
        try:
            envelope["data"] = json.loads(result.stdout)
        except (ValueError, TypeError):
            envelope["data"] = result.stdout.strip() or None
        if result.stderr.strip():
            envelope["stderr"] = result.stderr.strip()
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)


def _force_utf8_stdio() -> None:
    """管道/重定向场景下 stdout/stderr 可能是 cp936 等 ANSI 码页，
    统一重配为 UTF-8 + replace，保证任何输出（含中文、emoji、特殊符号）都不崩溃。
    交互控制台不受影响。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    try:
        if args.command == "info":
            _cmd_info(args)
            return 0

        if args.command in ("exists", "check"):
            return _cmd_exists(args)

        handler = _HANDLERS.get(args.command)
        if handler is None:
            parser.print_help()
            return 2

        result = handler(args)
    except OssutilNotFound as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except CertificationUnavailable as exc:
        print(f"凭证获取失败（ielym-certification）：{exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _emit(args, result)
    return result.code


if __name__ == "__main__":
    sys.exit(main())