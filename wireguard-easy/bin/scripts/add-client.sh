#!/usr/bin/env bash
# =============================================================================
# wireguard-easy :: 添加客户端（一键生成密钥/隧道IP/配置/二维码）
# 用法: sudo ./add-client.sh <设备名> [隧道IP]
# 例  : sudo ./add-client.sh laptop
#       sudo ./add-client.sh phone-xiaomi 10.0.0.4
# 输出: /root/wireguard-clients/<设备名>.conf + <设备名>.png（二维码）
# =============================================================================
set -euo pipefail

NAME="${1:?用法: sudo ./add-client.sh <设备名> [隧道IP]}"
# 文件名安全化（printf 避免 echo 的换行被 tr 转成 '-'）
NAME="$(printf '%s' "$NAME" | LC_ALL=C tr -c 'a-zA-Z0-9_-' '-')"

[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }
command -v wg >/dev/null || { echo "❌ 未安装 wireguard-tools，请先运行 install.sh"; exit 1; }
systemctl is-active --quiet wg-quick@wg0 || { echo "❌ wg0 未运行"; exit 1; }

CONF=/etc/wireguard/wg0.conf
SERVER_PUB=$(cat /etc/wireguard/server.pub)
LISTEN_PORT=$(awk -F'= ' '/^ListenPort/{print $2}' "$CONF")
GW_IP=$(awk -F'= ' '/^Address/{print $2}' "$CONF" | cut -d/ -f1)
SUBNET_PREFIX=$(echo "$GW_IP" | cut -d. -f1-3)
PUBLIC_ENDPOINT="${PUBLIC_ENDPOINT:-$(cat /etc/wireguard/public_endpoint 2>/dev/null || echo '')}"
OUTDIR=/root/wireguard-clients
mkdir -p "$OUTDIR"

# --- 生成客户端密钥对 -----------------------------------------------------
umask 077
CLIENT_KEY="$OUTDIR/${NAME}.key"
CLIENT_PUB="$OUTDIR/${NAME}.pub"
wg genkey > "$CLIENT_KEY"
wg pubkey < "$CLIENT_KEY" > "$CLIENT_PUB"
CLIENT_PUB=$(cat "$CLIENT_PUB")
chmod 600 "$CLIENT_KEY"

# --- 分配隧道 IP ----------------------------------------------------------
IP="${2:-}"
if [ -z "$IP" ]; then
  # 用 dump 格式取各 peer 的 allowed-ips（第4列，可能含逗号多 IP）
  # 注意: 首个客户端时 grep 无匹配返回 1，需 || true 以免 set -e 中断
  USED=$(wg show wg0 dump | awk -F'\t' '{print $4}' | tr ',' '\n' \
         | grep -oE '([0-9]+\.){3}[0-9]+' | sort -t. -k4 -n || true)
  for i in $(seq 2 254); do
    CAND="${SUBNET_PREFIX}.${i}"
    if ! echo "$USED" | grep -qx "$CAND"; then IP="$CAND"; break; fi
  done
fi
[ -n "$IP" ] || { echo "❌ 网段内无空闲 IP"; exit 1; }

# --- 热添加 + 持久化（幂等）---------------------------------------------
wg set wg0 peer "$CLIENT_PUB" allowed-ips "${IP}/32" persistent-keepalive 25
if ! grep -q "$CLIENT_PUB" "$CONF"; then
cat >> "$CONF" <<EOF

[Peer]
PublicKey = $CLIENT_PUB
AllowedIPs = ${IP}/32
PersistentKeepalive = 25
EOF
fi

# --- 生成客户端配置 -------------------------------------------------------
cat > "$OUTDIR/${NAME}.conf" <<EOF
[Interface]
PrivateKey = $(cat "$CLIENT_KEY")
Address = ${IP}/32
DNS = 223.5.5.5

[Peer]
PublicKey = ${SERVER_PUB}
Endpoint = ${PUBLIC_ENDPOINT}:${LISTEN_PORT}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
chmod 600 "$OUTDIR/${NAME}.conf"

# 无法探测到公网端点时提示手动填
if [ -z "$PUBLIC_ENDPOINT" ]; then
  echo "⚠️  未配置服务器公网 IP/域名，Endpoint 为空，请编辑 ${OUTDIR}/${NAME}.conf 或先 export PUBLIC_ENDPOINT=<公网IP> 再重跑"
fi

# --- 二维码 ---------------------------------------------------------------
qrencode -t PNG -o "$OUTDIR/${NAME}.png" < "$OUTDIR/${NAME}.conf" 2>/dev/null \
  && QR=yes || QR=no

echo
echo "✅ 客户端 [${NAME}] 已添加"
echo "────────────────────────────────────────────"
echo "  隧道 IP : ${IP}/32"
echo "  客户端公钥: ${CLIENT_PUB}"
echo "  配置文件: ${OUTDIR}/${NAME}.conf"
[ "$QR" = yes ] && echo "  二维码  : ${OUTDIR}/${NAME}.png （手机 App 扫码导入）"
echo "────────────────────────────────────────────"
echo "📱 手机: WireGuard App → + → 扫二维码"
echo "💻 电脑: 安装 WireGuard 客户端 → 导入 ${NAME}.conf → 激活"
echo ""
echo "安全提示: 私钥在 ${CLIENT_KEY}，只在设备与服务器间传递，勿外传。"
