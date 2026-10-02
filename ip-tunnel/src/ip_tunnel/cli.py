"""ip-tunnel CLI：快代理隧道代理（每一次请求换 IP）的命令行入口。

用法:
    ip-tunnel export [--raw]
    ip-tunnel request <url> [--method M] [--data D] [--header K:V] [--sid S]
                     [--channel N] [--retries R] [--timeout T] [--json]
    ip-tunnel test [--url U] [--sid S] [--json]
    ip-tunnel ip [--sid S] [--json]
    ip-tunnel limits
    ip-tunnel lock-help

隧道账号只从 OSS 凭证库取回（经 ielym-certification），本 CLI 不内嵌任何明文密钥。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from . import __version__
from .certification import (
    CredentialError,
    CredentialNotFound,
    get_credential,
    masked_summary,
)
from .http import build_proxy_url, http_request

DEFAULT_TEST_URL = "https://dev.kdlapi.com/testproxy"
# 隧道对部分域名（如 api.ipify.org / httpbin.org）会被目标拒绝返回 517，属目标相关、非瞬时，
# 重试无意义；故 ip 命令用多个实测可用的 IP 回显源并逐个回退。
DEFAULT_IP_URLS = [
    "https://ipinfo.io/ip",
    "https://ifconfig.me/ip",
    "https://api.ip.sb/ip",
    "http://ip.3322.net",
    "http://members.3322.org/dyndns/getip",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ip-tunnel",
        description=(
            "快代理隧道代理（IP 隧道）CLI：取回隧道账号并生成代理配置 / 通过隧道发起请求。"
            "每次请求换 IP；带自动重试与速率限制；凭据来自 OSS 凭证库，不写入代码。"
        ),
    )
    p.add_argument("-v", "--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command")

    e = sub.add_parser("export", help="打印隧道代理配置（默认屏蔽密码；--raw 输出可直接使用的 proxies JSON）")
    e.add_argument("--raw", action="store_true", help="输出含真实密码、可直接喂给 requests 的 proxies 配置 JSON")
    e.add_argument("--sid", help="锁 IP 用的附加串（password:sid，锁 30 秒），--raw 时生效")

    r = sub.add_parser("request", help="通过隧道发起一次 HTTP 请求（含重试与速率限制）")
    r.add_argument("url", help="目标 URL")
    r.add_argument("--method", default="GET", help="HTTP 方法，默认 GET")
    r.add_argument("--data", default=None, help="请求体（字符串，遵循 method 语义）")
    r.add_argument("--header", action="append", metavar="K:V", help="附加请求头，可多次（值需 URL 编码）")
    r.add_argument("--sid", default=None, help="锁 IP：同一字符串锁同一 IP 30 秒")
    r.add_argument("--channel", default=None, help="指定通道（仅 http；对应 kdl-tps-channel 头）")
    r.add_argument("--retries", type=int, default=3, help="瞬时失败最大重试次数，默认 3")
    r.add_argument("--timeout", type=float, default=30.0, help="单次请求超时（秒），默认 30")
    r.add_argument("--rate", type=float, default=None, help="覆盖请求速率限制（次/秒），默认用凭证配置 5")
    r.add_argument("--json", action="store_true", help="输出 JSON 信封")

    t = sub.add_parser("test", help="验证隧道可用性（HTTP 200 即成功）")
    t.add_argument("--url", default=DEFAULT_TEST_URL, help=f"测试目标，默认 {DEFAULT_TEST_URL}")
    t.add_argument("--sid", default=None)
    t.add_argument("--json", action="store_true")

    i = sub.add_parser("ip", help="打印隧道当前出口 IP（验证换 IP）")
    i.add_argument("--sid", default=None)
    i.add_argument("--json", action="store_true")

    s = sub.add_parser("limits", help="打印当前隧道的并发/带宽/换 IP/超带宽限制")
    s.add_argument("--json", action="store_true")

    s2 = sub.add_parser("lock-help", help="解释锁 IP（--sid）与多通道用法")
    return p


def _load_cred() -> dict:
    try:
        return get_credential()
    except CredentialNotFound:
        _err(
            "缺少必需凭据：OSS 凭证库未登记服务 ip-tunnel"
            "（ielym-certification api-key --name ip-tunnel，JSON 字段 tunnel/username/password）"
        )
    except CredentialError as e:
        _err(f"从 OSS 凭证库获取 ip-tunnel 凭据失败：{e}")
    raise SystemExit(1)  # 不可达；仅防静态检查


def _err(msg: str) -> None:
    print(f"错误：{msg}", file=sys.stderr)
    raise SystemExit(1)


def cmd_export(args) -> int:
    cred = _load_cred()
    if args.raw:
        proxy = build_proxy_url(cred, args.sid)
        out = {
            "service": cred["service"],
            "tunnel": cred["tunnel"],
            "username": cred["username"],
            "sid_locked": bool(args.sid),
            "proxies": {"http": proxy, "https": proxy},
            "rate_limit_per_sec": cred["rate_limit_per_sec"],
            "bandwidth_mbps": cred["bandwidth_mbps"],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        # 提醒：真实密码已输出到 stdout，勿写日志/提交仓库
        print(
            "提示：以上输出含真实密码，仅用于注入运行时，勿打印到日志或提交到仓库。",
            file=sys.stderr,
        )
        return 0

    s = masked_summary(cred)
    proxy = build_proxy_url(cred, args.sid)
    print(f"隧道地址   : {s['tunnel']}")
    print(f"用户名     : {s['username']}")
    print(f"密码       : {s['password']}")
    print(f"换 IP 模式 : {s['ip_rotation']}")
    print(f"并发限制   : {s['rate_limit_per_sec']} 次/s")
    print(f"带宽峰值   : {s['bandwidth_mbps']} Mbps")
    print(f"超带宽机制 : {s['bandwidth_overage']}")
    print(f"凭证来源   : oss://{s['service']}（{s['oss_path']}）")
    print()
    print("当前代理 URL（含 sid 锁 IP）：")
    print(f"  {proxy}")
    print("提示：如需在程序中直接使用，用 `ip-tunnel export --raw` 取 proxies JSON。")
    return 0


def _parse_headers(pairs) -> dict:
    headers = {}
    for item in pairs or []:
        if ":" not in item:
            _err(f"请求头格式应为 K:V，收到：{item}")
        k, _, v = item.partition(":")
        headers[k.strip()] = v.strip()
    return headers


def cmd_request(args) -> int:
    cred = _load_cred()
    headers = _parse_headers(args.header)
    res = http_request(
        args.method,
        args.url,
        cred=cred,
        sid=args.sid,
        channel=args.channel,
        headers=headers,
        data=args.data,
        retries=args.retries,
        timeout=args.timeout,
        rate=args.rate,
    )

    if args.json:
        body = res["body"].decode("utf-8", "replace") if res["body"] is not None else None
        envelope = {
            "url": args.url,
            "ok": res["ok"],
            "status": res["status"],
            "attempts": res["attempts"],
            "elapsed_ms": res["elapsed_ms"],
            "body": body,
            "reason": res["reason"],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        if res["ok"]:
            sys.stdout.buffer.write(res["body"] or b"")
            if res["body"] and not res["body"].endswith(b"\n"):
                sys.stdout.buffer.write(b"\n")
            return 0
        # 非 --json 失败时给可读错误
        _err(f"请求失败（重试 {args.retries} 次后仍失败）：{res['reason']}")
    return 0 if res["ok"] else 1


def cmd_test(args) -> int:
    cred = _load_cred()
    # 测试目标本身即返回文本 IP；重试逻辑会吸收 440/441/515/516/517 等单次失败
    res = http_request("GET", args.url, cred=cred, sid=args.sid, retries=3, timeout=30.0)
    if args.json:
        envelope = {
            "url": args.url,
            "ok": res["ok"],
            "status": res["status"],
            "attempts": res["attempts"],
            "body": res["body"].decode("utf-8", "replace") if res["body"] is not None else None,
            "reason": res["reason"],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    elif res["ok"]:
        print(f"隧道可用：GET {args.url} → HTTP {res['status']}（尝试 {res['attempts']} 次）")
        if res["body"]:
            print(f"返回内容：{res['body'].decode('utf-8', 'replace').strip()}")
    else:
        print(f"隧道不可用：{res['reason']}（尝试 {res['attempts']} 次）", file=sys.stderr)
    return 0 if res["ok"] else 1


def cmd_ip(args) -> int:
    cred = _load_cred()
    ip = None
    via = None
    reason = "所有 IP 回显源均不可达"
    for url in DEFAULT_IP_URLS:
        res = http_request("GET", url, cred=cred, sid=args.sid, retries=2, timeout=20.0)
        if res["ok"] and res["body"]:
            candidate = res["body"].decode("utf-8", "replace").strip()
            if candidate:
                ip = candidate[-64:]  # 防御性截断，避免被注入长串
                via = url
                break
        reason = res["reason"]
    if args.json:
        print(json.dumps({
            "ok": bool(ip),
            "ip": ip,
            "via": via,
            "reason": reason if not ip else None,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2))
    elif ip:
        print(ip)
        print(f"（探测源：{via}）", file=sys.stderr)
    else:
        print(f"未能取得出口 IP：{reason}", file=sys.stderr)
    return 0 if ip else 1


def cmd_limits(args) -> int:
    cred = _load_cred()
    if args.json:
        print(json.dumps(masked_summary(cred), ensure_ascii=False, indent=2))
        return 0
    s = masked_summary(cred)
    print(f"隧道       : {s['tunnel']}")
    print(f"换 IP 模式 : {s['ip_rotation']}")
    print(f"并发限制   : {s['rate_limit_per_sec']} 次/s")
    print(f"带宽峰值   : {s['bandwidth_mbps']} Mbps")
    print(f"超带宽机制 : {s['bandwidth_overage']}")
    print(f"提示       : 持续超频会收到 441，超带宽会收到 440；CLI 已按 {s['rate_limit_per_sec']} 次/s 排队。")
    return 0


def cmd_lock_help(args) -> int:
    cred = _load_cred()
    s = masked_summary(cred)
    print("一、锁 IP（同一字符串锁同一 IP 30 秒）")
    print("  在密码后拼接 :<任意字符串> 即可锁 IP；多用于需要同一 IP 的多请求场景（如登录）。")
    print("  用法：ip-tunnel request <url> --sid <串>")
    print(f"  验证：连续 `ip-tunnel ip --sid <同一串>` 两次应返回同一 IP。")
    print()
    print("二、多通道")
    print("  对换 IP 周期>=15 秒的隧道，可用 --channel <编号> 指定转发通道（仅 http）。")
    print("  用法：ip-tunnel request <url> --channel 3")
    print()
    print(f"三、当前隧道：{s['tunnel']}，并发 {s['rate_limit_per_sec']} 次/s，带宽 {s['bandwidth_mbps']} Mbps。")
    return 0


def _run(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "export": cmd_export,
        "request": cmd_request,
        "test": cmd_test,
        "ip": cmd_ip,
        "limits": cmd_limits,
        "lock-help": cmd_lock_help,
    }
    return handlers[args.command](args)


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"ip-tunnel 执行失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1