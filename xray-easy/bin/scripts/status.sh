#!/usr/bin/env bash
# =============================================================================
# xray-easy :: 查看服务与连接状态
# 用法: sudo ./status.sh [--json]
# =============================================================================
set -euo pipefail

XRAY_CONF=/usr/local/etc/xray/config.json
JSON=0
[ "${1:-}" = "--json" ] && JSON=1

if ! command -v xray >/dev/null 2>&1; then
  echo "❌ 未安装 xray"; exit 1
fi

ACTIVE=$(systemctl is-active xray 2>/dev/null || echo unknown)
PORT=$(python3 -c "import json;print(json.load(open('$XRAY_CONF'))['inbounds'][0]['port'])" 2>/dev/null || echo "?")
DEST=$(python3 -c "import json;print(json.load(open('$XRAY_CONF'))['inbounds'][0]['streamSettings']['realitySettings']['dest'])" 2>/dev/null || echo "?")

if [ "$JSON" = 1 ]; then
  CONNS=$(ss -tn 2>/dev/null | grep -c ":$PORT" || true)
  python3 - "$ACTIVE" "$PORT" "$DEST" "$CONNS" <<'EOF'
import json,sys
active,port,dest,conns=sys.argv[1:5]
print(json.dumps({"service":active,"port":port,"dest":dest,"estab_conns":conns}))
EOF
  exit 0
fi

echo "xray 服务 : $ACTIVE"
echo "监听端口  : TCP $PORT"
echo "伪装站点  : $DEST"
echo "──────────────────────────────"
echo "443 相关连接："
ss -tn | grep ":$PORT" | head -15 || echo "  (无)"
echo ""
echo "错误日志（最近10条）："
tail -n 10 /var/log/xray/error.log 2>/dev/null || echo "  (无)"
