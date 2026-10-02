#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sched —— 本地定时任务调度器 CLI。

设计边界：本 CLI 只做两件事
  1. 进程与服务层：serve（前台）/ start / stop / restart / status / init
  2. 调度器 HTTP API 的薄封装：任务 CRUD、立即执行、执行历史、日志、终止、重载、导出

不重复实现调度逻辑，任务内部实现也不属于本 CLI 的职责范围。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_HOME = Path("/mnt/data01/projects/scheduler")
CONF_PATH = Path.home() / ".sched.json"
UNIT_NAME = "scheduler.service"
UNIT_PATHS = (
    Path("/etc/systemd/system") / UNIT_NAME,
    Path("/etc/systemd/system/multi-user.target.wants") / UNIT_NAME,
    Path("/usr/lib/systemd/system") / UNIT_NAME,
)
DEFAULT_PORT = 8787
PID_FILE = "data/runtime/sched.pid"
SERVE_LOG = "data/runtime/serve.log"


# --------------------------------------------------------------------------- #
# 路径与配置
# --------------------------------------------------------------------------- #
def _conf() -> dict[str, Any]:
    try:
        return json.loads(CONF_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_home(override: str | None) -> Path:
    """按 --home > SCHED_HOME > ~/.sched.json > 默认值 的顺序定位调度器根目录。"""
    raw = override or os.environ.get("SCHED_HOME") or _conf().get("home") or str(DEFAULT_HOME)
    return Path(raw).expanduser().resolve()


def read_settings(home: Path) -> dict[str, Any]:
    try:
        return json.loads((home / "data" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def listen_endpoint(home: Path, args: argparse.Namespace) -> tuple[str, int]:
    """服务实际监听的地址（settings.http，--host/--port 可覆盖）。"""
    s = read_settings(home).get("http") or {}
    host = getattr(args, "host", None) or s.get("host") or "127.0.0.1"
    port = getattr(args, "port", None) or s.get("port") or DEFAULT_PORT
    return str(host), int(port)


def http_endpoint(home: Path, args: argparse.Namespace) -> tuple[str, int]:
    """客户端连接地址：监听通配地址时连本机回环。"""
    host, port = listen_endpoint(home, args)
    if host in ("0.0.0.0", "::", "*", ""):
        host = "127.0.0.1"
    return host, port


def base_url(home: Path, args: argparse.Namespace) -> str:
    if getattr(args, "url", None):
        return str(args.url).rstrip("/")
    host, port = http_endpoint(home, args)
    return f"http://{host}:{port}"


def lan_ip() -> str:
    """本机对内网卡 IP；取不到时退回回环。不发包，只让内核选出出口网卡。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def public_host() -> str:
    """浏览器能直连的地址：优先 SCHED_PUBLIC_HOST，其次云厂商元数据里的 EIP/公网 IP。

    云主机的内网 IP（如 172.31.x.x）本机之外不可达，直接给用户是打不开的。
    元数据探测仅 1s 超时、无外网依赖，取不到就返回空串由调用方兜底。
    """
    override = os.environ.get("SCHED_PUBLIC_HOST")
    if override:
        return override.strip()
    for url in (
        "http://100.100.100.200/latest/meta-data/eipv4",      # 阿里云 EIP
        "http://100.100.100.200/latest/meta-data/public-ipv4",  # 阿里云经典公网 IP
    ):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                ip = r.read().decode().strip()
            if ip and ip.count(".") == 3:
                return ip
        except Exception:
            continue
    return ""


def web_url(home: Path, args: argparse.Namespace) -> str:
    """Web UI 地址：监听通配地址时换成公网地址；地址里不带 token。"""
    host, port = listen_endpoint(home, args)
    if host in ("0.0.0.0", "::", "*", ""):
        host = public_host() or lan_ip()
    elif host in ("localhost", "::1"):
        host = "127.0.0.1"
    return f"http://{host}:{port}/"


def resolve_token(home: Path, args: argparse.Namespace) -> str:
    if getattr(args, "token", None):
        return str(args.token)
    if os.environ.get("SCHED_TOKEN"):
        return os.environ["SCHED_TOKEN"]
    auth = read_settings(home).get("auth") or {}
    return str(auth.get("token") or "")


# --------------------------------------------------------------------------- #
# 输出工具
# --------------------------------------------------------------------------- #
def _dw(text: str) -> int:
    """终端显示宽度（CJK 记 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _dw(text))


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    if not rows:
        print("（无数据）")
        return
    cols = list(zip(headers, *rows)) if rows else []
    widths = [max(_dw(str(c)) for c in col) for col in cols]
    print("  ".join(_pad(h, w) for h, w in zip(headers, widths)).rstrip())
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(_pad(str(c), w) for c, w in zip(row, widths)).rstrip())


def emit(payload: Any, args: argparse.Namespace) -> None:
    """--json 时输出原始 JSON，否则交由调用方的表格逻辑处理。"""
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def die(msg: str, code: int = 1) -> "None":
    print(f"错误：{msg}", file=sys.stderr)
    raise SystemExit(code)


# --------------------------------------------------------------------------- #
# HTTP 客户端
# --------------------------------------------------------------------------- #
def _request(home: Path, args: argparse.Namespace, path: str, method: str = "GET",
             body: Any = None, query: dict[str, Any] | None = None) -> tuple[int, bytes | str]:
    """底层请求：返回 (status_code, bytes)；网络不可达时 status=0，payload 为错误原因。

    本函数只描述事实，不打印、不退出 —— 由 api() 决定如何呈现。
    """
    url = base_url(home, args) + path
    if query:
        clean = {k: v for k, v in query.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    token = resolve_token(home, args)
    if token:
        headers["X-Sched-Token"] = token

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def api(home: Path, args: argparse.Namespace, path: str, method: str = "GET",
        body: Any = None, query: dict[str, Any] | None = None, raw: bool = False) -> Any:
    status, blob = _request(home, args, path, method=method, body=body, query=query)
    if status == 0:
        die(f"无法连接调度器 {base_url(home, args)}：{blob}\n"
            f"（服务未启动？先执行 `sched start`，或 `sched serve` 前台运行）", 2)
    if status >= 400:
        detail = blob.decode("utf-8", "replace") if isinstance(blob, bytes) else str(blob)
        try:
            detail = json.loads(detail).get("detail") or detail
        except json.JSONDecodeError:
            pass
        if status == 401:
            die(f"鉴权失败（401）。请带 --token，或确认本机回环免 token 已开启。\n{detail}", 2)
        die(f"HTTP {status}：{detail}")

    if raw:
        return blob
    try:
        return json.loads(blob or b"null")
    except json.JSONDecodeError:
        return blob.decode("utf-8", "replace") if isinstance(blob, bytes) else blob


def api_try(home: Path, args: argparse.Namespace, path: str, method: str = "GET") -> Any | None:
    """同 api()，但失败返回 None（不打印、不退出）—— 用于「先探测再决定」的场景。"""
    status, blob = _request(home, args, path, method=method)
    if status != 200:
        return None
    try:
        return json.loads(blob or b"null")
    except json.JSONDecodeError:
        return None


def api_alive(home: Path, args: argparse.Namespace) -> dict[str, Any] | None:
    d = api_try(home, args, "/api/health")
    return d if isinstance(d, dict) and d.get("ok") else None


# --------------------------------------------------------------------------- #
# 服务控制
# --------------------------------------------------------------------------- #
def _systemd_available() -> bool:
    return bool(shutil.which("systemctl")) and any(p.exists() for p in UNIT_PATHS)


def _pid_path(home: Path) -> Path:
    return home / PID_FILE


def _read_pid(home: Path) -> int | None:
    try:
        return int(_pid_path(home).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def _wait_health(home: Path, args: argparse.Namespace, timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if api_alive(home, args):
            return True
        time.sleep(0.4)
    return False


def cmd_init(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    home.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "scheduler", "init"], cwd=str(home))
    if r.returncode != 0:
        die("初始化失败：`python3 -m scheduler init` 退出码非 0", r.returncode)
    CONF_PATH.write_text(json.dumps({"home": str(home)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已记录源目录：{CONF_PATH}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if not (home / "scheduler" / "__init__.py").exists():
        die(f"{home} 不是调度器目录（缺 scheduler/__init__.py）")
    host, port = listen_endpoint(home, args)
    cmd = [sys.executable, "-m", "scheduler", "serve", "--host", host, "--port", str(port)]
    if args.log_level:
        cmd += ["--log-level", args.log_level]
    print(f"Web UI   {web_url(home, args)}", flush=True)
    os.chdir(home)
    os.execv(sys.executable, cmd)  # 前台接管，交给 systemd / Ctrl-C


def cmd_start(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if not (home / "scheduler" / "__init__.py").exists():
        die(f"{home} 不是调度器目录（缺 scheduler/__init__.py）")
    if api_alive(home, args):
        print(f"已在运行：{base_url(home, args)}")
        print(f"Web UI   {web_url(home, args)}")
        return 0

    if _systemd_available():
        r = subprocess.run(["systemctl", "start", UNIT_NAME])
        if r.returncode != 0:
            die("systemctl start 失败", r.returncode)
        if _wait_health(home, args):
            print("已通过 systemd 启动，健康检查通过")
            print(f"Web UI   {web_url(home, args)}")
            return 0
        print("systemd start 成功，但健康检查未通过；请查看 journalctl -u " + UNIT_NAME, file=sys.stderr)
        return 1

    pid = _read_pid(home)
    if _pid_alive(pid) and api_alive(home, args):
        print(f"已在运行（pid={pid}）")
        return 0

    host, port = listen_endpoint(home, args)
    log_path = home / SERVE_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "scheduler", "serve", "--host", host, "--port", str(port)],
        cwd=str(home), stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _pid_path(home).write_text(str(proc.pid), encoding="utf-8")

    if _wait_health(home, args):
        print(f"已启动 pid={proc.pid}  {base_url(home, args)}")
        print(f"Web UI   {web_url(home, args)}")
        print(f"日志：{log_path}")
        return 0
    print(f"启动失败或超时，pid={proc.pid}；日志：{log_path}", file=sys.stderr)
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if _systemd_available():
        r = subprocess.run(["systemctl", "stop", UNIT_NAME])
        if r.returncode != 0:
            die("systemctl stop 失败", r.returncode)
        print("已通过 systemd 停止")
        return 0

    pid = _read_pid(home)
    if not _pid_alive(pid):
        _pid_path(home).unlink(missing_ok=True)
        print("未在运行")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _pid_path(home).unlink(missing_ok=True)
        print("未在运行")
        return 0

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.4)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)
        print(f"已强制终止 pid={pid}（SIGTERM 超时）")
    else:
        print(f"已停止 pid={pid}")
    _pid_path(home).unlink(missing_ok=True)
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    time.sleep(0.6)
    return cmd_start(args)


def cmd_status(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    health = api_alive(home, args)
    pid = _read_pid(home)
    mode = "systemd" if _systemd_available() else ("pidfile" if _pid_alive(pid) else "-")

    if getattr(args, "json", False):
        emit({"running": health is not None, "mode": mode, "pid": pid if _pid_alive(pid) else None,
              "url": base_url(home, args), "web_url": web_url(home, args),
              "health": health}, args)
        return 0 if health else 1

    lh, lp = listen_endpoint(home, args)
    print(f"根目录   {home}")
    print(f"地址     {base_url(home, args)}")
    print(f"监听     {lh}:{lp}")
    print(f"Web UI   {web_url(home, args)}")
    print(f"托管方式 {mode}" + (f"（pid={pid}）" if _pid_alive(pid) else ""))
    if not health:
        print("状态     未运行")
        return 1
    c = health.get("counts", {})
    print(f"状态     运行中  since {health.get('started_at')}  timezone={health.get('timezone')}")
    print(f"引擎     {'已启动' if health.get('engine_running') else '未启动'}")
    print(f"任务     {c.get('jobs_ok')}/{c.get('jobs')} 可用   启用 {c.get('jobs_enabled')}   在途 {c.get('active')}")
    mem = health.get("scheduler_memory") or {}
    if mem:
        print_table(["任务", "下次触发"], [[k, str(v)] for k, v in sorted(mem.items())])
    return 0


# --------------------------------------------------------------------------- #
# 任务管理
# --------------------------------------------------------------------------- #
def _sched_desc(job: dict[str, Any]) -> str:
    """把 schedule 渲染成人话（与 Web UI 保持一致）；识别不了就退回原始表达式。"""
    eff = job.get("effective") or job.get("schedule") or {}
    t = eff.get("type") or "manual"
    if t == "interval":
        if eff.get("start_time") and eff.get("end_time"):
            phrase = _weekdays_phrase(eff.get("weekdays"))
            start = eff.get("start_time") or "?"
            end = eff.get("end_time") or "?"
            if _cross_day(start, end):
                end = f"次日 {end}"
            tail = "窗口外允许跑完" if eff.get("allow_overrun") else "窗口到点终止在途"
            if eff.get("interval"):
                return f"{phrase} {start}–{end} 窗内每 {_fmt_duration(eff.get('interval'))}（{tail}）".strip()
            return f"{phrase} {start}–{end} 窗口起点执行一次（{tail}）"
        dur = _fmt_duration(eff.get("interval"))
        return f"每 {dur}" if dur else f"每 {eff.get('interval')}s"
    if t == "once":
        return f"一次 {eff.get('once_at')}"
    return "仅手动"


def _cross_day(start: Any, end: Any) -> bool:
    """end_time 早于 start_time = 窗口跨到次日（星期按窗口起点那天算）。"""

    def sec(v: Any) -> int | None:
        s = str(v or "")
        parts = s.split(":")
        if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
            return None
        h, m = int(parts[0]), int(parts[1])
        ss = int(parts[2]) if len(parts) == 3 else 0
        return h * 3600 + m * 60 + ss

    a, b = sec(start), sec(end)
    return a is not None and b is not None and b < a


_WEEKDAY_CN = "一二三四五六日"


def _fmt_duration(sec: Any) -> str:
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h} 小时")
    if m:
        parts.append(f"{m} 分" if s else f"{m} 分钟")
    if s:
        parts.append(f"{s} 秒")
    return " ".join(parts)


def _weekdays_phrase(days: Any) -> str:
    try:
        s = sorted({int(x) for x in (days or [])})
    except (TypeError, ValueError):
        return "每天"
    if not s or len(s) == 7:
        return "每天"
    contiguous = all(s[i] == s[i - 1] + 1 for i in range(1, len(s)))
    if contiguous and len(s) >= 3:
        return f"每周{_WEEKDAY_CN[s[0] - 1]}至{_WEEKDAY_CN[s[-1] - 1]}"
    return "每周" + "、".join(_WEEKDAY_CN[d - 1] for d in s)


def _job_row(j: dict[str, Any]) -> list[str]:
    last = j.get("last_run") or {}
    last_s = f"{last.get('status', '-')}"
    if last.get("finished_at"):
        last_s += f" {str(last['finished_at'])[:19].replace('T', ' ')}"
    return [
        str(j.get("job_id", "")),
        str(j.get("name", "")),
        _sched_desc(j),
        str(j.get("priority", 0)),
        "启用" if j.get("enabled") else "停用",
        str(j.get("next_run_at") or "—")[:19].replace("T", " "),
        last_s,
    ]


JOB_HEADERS = ["任务ID", "名称", "调度", "优先级", "启用", "下次触发", "上次结果"]


def cmd_job_ls(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    data = api(home, args, "/api/jobs")
    jobs = data.get("jobs", [])
    if getattr(args, "json", False):
        emit(data, args)
        return 0
    print_table(JOB_HEADERS, [_job_row(j) for j in jobs])
    bad = [j for j in jobs if not j.get("ok")]
    for j in bad:
        print(f"\n[清单异常] {j['job_id']}: {j.get('error')}", file=sys.stderr)
    return 0


def cmd_job_new(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    data = api(home, args, "/api/jobs", method="POST", body={"name": args.name})
    if getattr(args, "json", False):
        emit(data, args)
        return 0
    print(f"已注册任务 {data.get('job_id')}  目录：{data.get('task_dir')}")
    print("提示：目录需已存在（含 task.json 与入口文件），调度器不生成任何文件；改完 task.json 执行 `sched reload`")
    return 0


def cmd_job_show(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    d = api(home, args, f"/api/jobs/{urllib.parse.quote(args.job_id)}")
    if getattr(args, "json", False):
        emit(d, args)
        return 0
    print(f"任务      {d.get('job_id')}  ({d.get('name')})")
    print(f"目录      {d.get('task_dir')}")
    print(f"入口      {d.get('entry_file') or '—'}")
    print(f"调度      {_sched_desc(d)}    启用：{'是' if d.get('enabled') else '否'}")
    print(f"优先级    {d.get('priority', 0)}   下次触发：{d.get('next_run_at') or '—'}")
    st = d.get("task_state") or {}
    if st:
        print(f"任务侧    状态 {st.get('status')}  loop {st.get('loop_count')}  步骤 {st.get('current_step')}")
        if st.get("last_error"):
            print(f"最近错误  {st['last_error']}")
    return 0


def cmd_job_rm(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    q = {"purge": "true" if args.purge else "false"}
    data = api(home, args, f"/api/jobs/{urllib.parse.quote(args.job_id)}", method="DELETE", query=q)
    if getattr(args, "json", False):
        emit(data, args)
        return 0
    print(f"已删除任务 {args.job_id}" + ("（含任务目录）" if args.purge else "（任务目录保留）") + "，执行历史与日志已同步删除")
    return 0


def _set_enabled(args: argparse.Namespace, enabled: bool) -> int:
    home = resolve_home(args.home)
    act = "enable" if enabled else "disable"
    api(home, args, f"/api/jobs/{urllib.parse.quote(args.job_id)}/{act}", method="POST")
    print(f"已{'启用' if enabled else '停用'} {args.job_id}")
    return 0


def cmd_job_enable(args: argparse.Namespace) -> int:
    return _set_enabled(args, True)


def cmd_job_disable(args: argparse.Namespace) -> int:
    return _set_enabled(args, False)


# --------------------------------------------------------------------------- #
# 执行 / 历史 / 日志
# --------------------------------------------------------------------------- #
def cmd_run(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    rec = api(home, args, f"/api/jobs/{urllib.parse.quote(args.job_id)}/run", method="POST",
              query={"dry_run": "true"} if args.dry_run else None)
    if getattr(args, "json", False):
        emit(rec, args)
        return 0
    tag = "  [DRY-RUN 调试，不产生真实副作用]" if args.dry_run else ""
    print(f"已入队  run_id={rec.get('run_id')}  job={rec.get('job_id')}  状态={rec.get('status')}{tag}")
    if rec.get("skipped"):
        print(f"本次触发未入队：{rec.get('reason')}")
        print(f"任务 {rec.get('job_id')} 正在运行/已满，本次触发已跳过（不影响下次触发）")
        return 0
    print(f"跟踪：sched log {rec.get('run_id')} -f    或 sched runs --job {rec.get('job_id')}")
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    data = api(home, args, "/api/runs", query={"job_id": args.job, "status": args.status, "limit": args.limit})
    if getattr(args, "json", False):
        emit(data, args)
        return 0
    active = data.get("active", [])
    if active:
        print(f"在途（{len(active)}）")
        print_table(["run_id", "任务", "触发", "状态", "pid", "已运行"],
                    [[r.get("run_id", ""), r.get("job_id", ""), r.get("trigger", "") + (" DRY" if r.get("dry_run") else ""),
                      r.get("status", ""), str(r.get("pid") or "-"), _dur(r.get("started_at"))] for r in active])
        print()
    hist = data.get("history", [])
    print(f"已完结（{len(hist)}）")
    print_table(["run_id", "任务", "触发", "状态", "退出码", "排队", "耗时", "计划时间", "说明"],
                [[r.get("run_id", ""), r.get("job_id", ""), r.get("trigger", "") + (" DRY" if r.get("dry_run") else ""),
                  r.get("status", ""), str(r.get("exit_code") if r.get("exit_code") is not None else "—"),
                  _ms(r.get("wait_ms")), _ms(r.get("duration_ms")),
                  str(r.get("scheduled_at") or "")[:19].replace("T", " "), r.get("reason") or ""] for r in hist])
    return 0


def _ms(v: Any) -> str:
    try:
        return f"{int(v) / 1000:.0f}s"
    except (TypeError, ValueError):
        return "—"


def _dur(started: Any) -> str:
    if not started:
        return "—"
    try:
        t0 = time.mktime(time.strptime(str(started)[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return "—"
    return f"{max(0, int(time.time() - t0))}s"


def cmd_log(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    if getattr(args, "follow", False):
        seen = 0
        try:
            while True:
                d = api(home, args, f"/api/runs/{urllib.parse.quote(args.run_id)}/log",
                        query={"stream": args.stream, "offset": seen})
                chunk = d.get("content") or ""
                if chunk:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    seen = d.get("offset", seen)
                rec = api(home, args, f"/api/runs/{urllib.parse.quote(args.run_id)}")
                if not rec.get("running"):
                    print(f"\n[run 已结束：{rec.get('record', {}).get('status')}]")
                    return 0
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 0
    d = api(home, args, f"/api/runs/{urllib.parse.quote(args.run_id)}/log",
            query={"stream": args.stream, "tail": args.tail})
    content = d.get("content") or ""
    sys.stdout.write(content)
    if content and not content.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    target = args.target

    # target 是一次在途 run_id → 只终止该 run；否则按 job_id 终止全部在途 run
    rec = api_try(home, args, f"/api/runs/{urllib.parse.quote(target)}")

    if rec is not None and rec.get("running"):
        api(home, args, f"/api/runs/{urllib.parse.quote(target)}/kill", method="POST")
        print(f"已发送终止信号：run {target}")
        return 0

    res = api(home, args, f"/api/jobs/{urllib.parse.quote(target)}/kill", method="POST")
    killed = res.get("killed") or []
    print(f"已终止任务 {target} 的在途 run：{len(killed)} 个")
    return 0


def cmd_task_state(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    d = api(home, args, f"/api/jobs/{urllib.parse.quote(args.job_id)}/task-state")
    print(json.dumps(d or {}, ensure_ascii=False, indent=2))
    return 0


def cmd_reload(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    info = api(home, args, "/api/reload", method="POST")
    if getattr(args, "json", False):
        emit(info, args)
        return 0
    print(f"已刷新：已注册任务 {info.get('jobs')} 个，可用 {info.get('ok')} 个（只刷新已注册项，不扫描新目录）")
    for j in info.get("errors", []):
        print(f"  [异常] {j}", file=sys.stderr)
    for k, v in sorted((info.get("memory") or {}).items()):
        print(f"  {k}  下次 {v}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    home = resolve_home(args.home)
    blob = api(home, args, "/api/export/runs.csv", query={"job_id": args.job}, raw=True)
    if args.output:
        Path(args.output).write_bytes(blob)
        print(f"已写入 {args.output}（{len(blob)} 字节）")
    else:
        sys.stdout.write(blob.decode("utf-8-sig", "replace"))
    return 0


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #
def _add_conn(p: argparse.ArgumentParser) -> None:
    p.add_argument("--home", help=f"调度器根目录（默认 {DEFAULT_HOME}）")
    p.add_argument("--url", help="直接指定服务地址，如 http://127.0.0.1:8787")
    p.add_argument("--host", help="覆盖 host（仅反查服务地址用）")
    p.add_argument("--port", type=int, help="覆盖 port")
    p.add_argument("--token", help="鉴权 token（默认读 data/settings.json）")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sched",
        description="本地定时任务调度器 CLI：启停服务、管理任务、查看执行历史与日志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  sched init                          # 建目录骨架并记录根目录
  sched serve                         # 前台启动（systemd 用）
  sched start / stop / restart        # 后台启动 / 停止 / 重启
  sched status                        # 运行状态与下次触发
  sched job ls                        # 列出任务
  sched job new my_task               # 注册已存在的 tasks/my_task/ 目录
  sched job show hello_task           # 详情（调度 / 状态 / 下次触发）
  sched job disable hello_task
  sched run hello_task                # 立即执行（CLI 专用，Web 不提供）
  sched runs --job hello_task -n 20   # 执行历史
  sched log <run_id> --stream stderr -f
  sched kill <run_id>                 # 终止一次 run（或 sched kill <job_id> 终止全部）
  sched task-state hello_task         # 任务侧 cache/state.json
  sched reload                        # 刷新已注册项（不扫描新目录）
  sched export runs --output runs.csv
""",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="建目录与 settings.json，并记录根目录")
    _add_conn(s)
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("serve", help="前台启动服务（systemd 调用）")
    _add_conn(s)
    s.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    s.set_defaults(func=cmd_serve)

    for name, fn, help_text in (("start", cmd_start, "后台启动服务"),
                                ("stop", cmd_stop, "停止服务"),
                                ("restart", cmd_restart, "重启服务")):
        s = sub.add_parser(name, help=help_text)
        _add_conn(s)
        s.set_defaults(func=fn)

    s = sub.add_parser("status", help="服务状态与下次触发")
    _add_conn(s)
    s.set_defaults(func=cmd_status)

    # job
    j = sub.add_parser("job", help="任务管理")
    jsub = j.add_subparsers(dest="sub", required=True)

    s = jsub.add_parser("ls", help="列出任务"); _add_conn(s); s.set_defaults(func=cmd_job_ls)
    s = jsub.add_parser("new", help="注册已有任务目录（不生成文件）")
    _add_conn(s)
    s.add_argument("name", help="任务 id（= tasks/<name>/ 目录名，需已存在且含 task.json）")
    s.set_defaults(func=cmd_job_new)

    s = jsub.add_parser("show", help="任务详情"); _add_conn(s)
    s.add_argument("job_id"); s.set_defaults(func=cmd_job_show)

    s = jsub.add_parser("rm", help="删除任务")
    _add_conn(s)
    s.add_argument("job_id")
    s.add_argument("--purge", action="store_true", help="同时删除任务目录（历史与日志删除任务时默认同步删除）")
    s.set_defaults(func=cmd_job_rm)

    s = jsub.add_parser("enable", help="启用任务"); _add_conn(s)
    s.add_argument("job_id"); s.set_defaults(func=cmd_job_enable)

    s = jsub.add_parser("disable", help="停用任务"); _add_conn(s)
    s.add_argument("job_id"); s.set_defaults(func=cmd_job_disable)

    # run / runs / log / kill
    s = sub.add_parser("run", help="立即执行一次任务（--dry-run 调试模式，不产生真实副作用）")
    _add_conn(s); s.add_argument("job_id"); s.add_argument("--dry-run", action="store_true",
        help="DRY-RUN 调试：注入 SCHED_DRY_RUN=1，任务代码必须跳过所有真实副作用（OSS 上传/写库/付费等），只打印动作")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("runs", help="执行历史")
    _add_conn(s)
    s.add_argument("--job", help="按任务过滤")
    s.add_argument("--status", help="按状态过滤 success|failed|timeout|killed|interrupted")
    s.add_argument("-n", "--limit", type=int, default=20, help="条数（默认 20）")
    s.set_defaults(func=cmd_runs)

    s = sub.add_parser("log", help="查看某次 run 的 stdout/stderr 日志")
    _add_conn(s)
    s.add_argument("run_id")
    s.add_argument("--stream", default="stdout", choices=["stdout", "stderr"])
    s.add_argument("--tail", type=int, default=0, help="只看末尾 N 行（0=全部）")
    s.add_argument("-f", "--follow", action="store_true", help="持续跟踪到 run 结束")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("kill", help="终止在途 run（传 run_id）或任务全部在途 run（传 job_id）")
    _add_conn(s); s.add_argument("target"); s.set_defaults(func=cmd_kill)

    s = sub.add_parser("task-state", help="读取任务侧 cache/state.json")
    _add_conn(s); s.add_argument("job_id"); s.set_defaults(func=cmd_task_state)

    s = sub.add_parser("reload", help="重扫 tasks/ 并重建调度")
    _add_conn(s); s.set_defaults(func=cmd_reload)

    e = sub.add_parser("export", help="导出")
    esub = e.add_subparsers(dest="sub", required=True)
    s = esub.add_parser("runs", help="导出执行历史 CSV")
    _add_conn(s)
    s.add_argument("--job", help="按任务过滤")
    s.add_argument("--output", help="写入文件（默认输出到 stdout）")
    s.set_defaults(func=cmd_export)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())