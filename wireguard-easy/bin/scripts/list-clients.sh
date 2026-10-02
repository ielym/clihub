#!/usr/bin/env bash
# wireguard-easy :: 列出客户端
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }
echo "== 运行中的 peers =="
wg show wg0 | grep -E 'peer|allowed ips|latest handshake|transfer|endpoint' || true
echo
echo "== 已生成的客户端文件 =="
ls -l /root/wireguard-clients/*.conf 2>/dev/null || echo "（无，先运行 add-client.sh）"
