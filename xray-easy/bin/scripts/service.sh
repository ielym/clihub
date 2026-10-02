#!/usr/bin/env bash
# =============================================================================
# xray-easy :: 服务管理（start/stop/restart/log）
# 用法: sudo ./service.sh {start|stop|restart|log [行数]}
# =============================================================================
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }

CMD="${1:-status}"
case "$CMD" in
  start)   systemctl start xray && systemctl is-active xray ;;
  stop)    systemctl stop xray && echo "xray 已停止" ;;
  restart) systemctl restart xray && sleep 1 && systemctl is-active xray ;;
  log)
    N="${2:-30}"
    echo "=== access.log ==="; tail -n "$N" /var/log/xray/access.log 2>/dev/null || echo "(空)"
    echo "=== error.log ==="; tail -n "$N" /var/log/xray/error.log 2>/dev/null || echo "(空)"
    ;;
  *) echo "用法: $0 {start|stop|restart|log [行数]}"; exit 1 ;;
esac
