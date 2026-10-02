#!/usr/bin/env bash
# =============================================================================
# wireguard-easy :: 服务器一键部署
# 用法: sudo ./install.sh <公网IP或域名> [端口=51820] [隧道网段=10.0.0.0/24]
# 例  : sudo ./install.sh 43.110.43.207
#       sudo ./install.sh vpn.example.com 51820 10.0.0.0/24
# 幂等: 已部署过则提示跳过（用 --force 可覆盖重建，危险，慎用）
# =============================================================================
set -euo pipefail

PUBLIC_ENDPOINT="${1:?用法: sudo ./install.sh <公网IP或域名> [端口] [网段]}"
LISTEN_PORT="${2:-51820}"
SUBNET="${3:-10.0.0.0/24}"

# --- 校验 ----------------------------------------------------------------
[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行: sudo ./install.sh"; exit 1; }

if systemctl is-active --quiet wg-quick@wg0 2>/dev/null && [ "${FORCE:-}" != "1" ]; then
  echo "⚠️  wg0 已处于运行状态。"
  echo "   如需重新部署请先: systemctl stop wg-quick@wg0 && FORCE=1 ./install.sh $*"
  echo "   服务器公钥: $(wg show wg0 public-key 2>/dev/null || cat /etc/wireguard/server.pub)"
  exit 0
fi

# --- 安装依赖 ------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y wireguard wireguard-tools qrencode

# --- 服务器密钥对（重复执行不覆盖已有密钥）-------------------------------
umask 077
mkdir -p /etc/wireguard
if [ ! -f /etc/wireguard/server.key ]; then
  wg genkey > /etc/wireguard/server.key
fi
wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub
chmod 600 /etc/wireguard/server.key

SERVER_PUB=$(cat /etc/wireguard/server.pub)
GW_IP=$(echo "$SUBNET" | cut -d. -f1-3).1
DEFAULT_IF=$(ip route show default | awk '{print $5; exit}')

# --- 保存公网端点（供 add-client.sh 生成客户端配置用）-------------------
echo "$PUBLIC_ENDPOINT" > /etc/wireguard/public_endpoint

# --- 写入 wg0.conf --------------------------------------------------------
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = ${GW_IP}/24
ListenPort = ${LISTEN_PORT}
PrivateKey = $(cat /etc/wireguard/server.key)
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o ${DEFAULT_IF} -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o ${DEFAULT_IF} -j MASQUERADE
EOF
chmod 600 /etc/wireguard/wg0.conf

# --- IP 转发（Ubuntu 24.04+ 无 /etc/sysctl.conf，写 sysctl.d）-------------
cat > /etc/sysctl.d/99-wireguard.conf <<'EOF'
net.ipv4.ip_forward = 1
EOF
sysctl --system >/dev/null

# --- 启动 + 自启 ----------------------------------------------------------
systemctl enable --now wg-quick@wg0

echo
echo "✅ 服务端部署完成"
echo "────────────────────────────────────────────"
echo "  隧道网段 : ${SUBNET}  (服务端 ${GW_IP})"
echo "  监听端口 : UDP ${LISTEN_PORT}"
echo "  服务器公钥: ${SERVER_PUB}"
echo "  出口网卡 : ${DEFAULT_IF}  (NAT MASQUERADE)"
echo "────────────────────────────────────────────"
echo "🚨 下一步（云服务器必做）:"
echo "   在云控制台安全组放行 UDP ${LISTEN_PORT} 入站，否则客户端握手无响应。"
echo ""
echo "🚀 添加客户端:  sudo ./add-client.sh <设备名>"
echo "   例        :  sudo ./add-client.sh laptop"
echo "               sudo ./add-client.sh phone-xiaomi"
echo ""
echo "📌 客户端配置与二维码将生成在: /root/wireguard-clients/"
