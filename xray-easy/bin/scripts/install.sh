#!/usr/bin/env bash
# =============================================================================
# xray-easy :: 安装 Xray 并部署 VLESS+Reality 服务端（幂等）
# 用法: sudo ./install.sh [--dest 站点:端口] [--port 端口] [--force]
# 例  : sudo ./install.sh
#       sudo ./install.sh --dest www.cloudflare.com:443 --port 443
# 输出: 打印 UUID / Reality PublicKey / shortId / dest / 端口（客户端配置用）
# =============================================================================
set -euo pipefail

DEST="www.cloudflare.com:443"
PORT=443
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)  DEST="$2"; shift 2 ;;
    --port)  PORT="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "未知参数: $1 (支持 --dest 站点:端口 --port 端口 --force)"; exit 1 ;;
  esac
done

[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }

XRAY_CONF=/usr/local/etc/xray/config.json
SNI="${DEST%%:*}"   # 去掉端口，得到 SNI 域名

# --- 安装 / 检查 Xray -------------------------------------------------------
if ! command -v xray >/dev/null 2>&1; then
  echo "▶ 安装 Xray（官方脚本）..."
  bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
fi
XRAY_VER=$(xray version | head -1)
echo "✅ Xray: $XRAY_VER"

# --- 幂等保护 ---------------------------------------------------------------
if [ -f "$XRAY_CONF" ] && [ "$FORCE" != 1 ]; then
  echo "⚠️  已存在 $XRAY_CONF，跳过生成（如需重建加 --force；重建后所有客户端须重新导入）"
  systemctl start xray 2>/dev/null || true
  xray run -test -c "$XRAY_CONF" >/dev/null 2>&1 && echo "✅ 配置校验通过"
  exit 0
fi

# --- 生成 Reality 密钥对 ----------------------------------------------------
echo "▶ 生成 x25519 密钥对 ..."
KEY_OUT=$(xray x25519)
# v26 输出格式为带冒号的 "PrivateKey:" / "Password (PublicKey):"；旧版为 "Private key"/"Public key"
PRIV_KEY=$(printf '%s\n' "$KEY_OUT" | sed -n 's/^PrivateKey: //p' | sed -n 's/^Private key: //p')
PUB_KEY=$(printf '%s\n' "$KEY_OUT" | sed -n 's/^Password (PublicKey): //p' | sed -n 's/^Public key: //p')
[ -z "$PRIV_KEY" ] && { echo "❌ 无法解析 x25519 私钥，输出: $KEY_OUT"; exit 1; }
[ -z "$PUB_KEY" ] && { echo "❌ 无法解析 x25519 公钥，输出: $KEY_OUT"; exit 1; }

# --- UUID / shortId ---------------------------------------------------------
UUID=$(xray uuid 2>/dev/null || cat /proc/sys/kernel/random/uuid)
SHORT_ID=$(openssl rand -hex 4 2>/dev/null || echo "3cf594f7")

# --- 写入服务端配置 ---------------------------------------------------------
umask 077
mkdir -p "$(dirname "$XRAY_CONF")"
cat > "$XRAY_CONF" <<EOF
{
  "log": {"loglevel": "warning", "access": "/var/log/xray/access.log", "error": "/var/log/xray/error.log"},
  "inbounds": [{
    "listen": "0.0.0.0",
    "port": $PORT,
    "protocol": "vless",
    "settings": {
      "clients": [{"id": "$UUID", "flow": "xtls-rprx-vision"}],
      "decryption": "none"
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "show": false,
        "dest": "$DEST",
        "xver": 0,
        "serverNames": ["$SNI"],
        "privateKey": "$PRIV_KEY",
        "shortIds": ["$SHORT_ID"]
      }
    },
    "sniffing": {"enabled": true, "destOverride": ["http", "tls", "quic"]}
  }],
  "outbounds": [{"protocol": "freedom", "tag": "direct"}]
}
EOF
chmod 644 "$XRAY_CONF"
mkdir -p /var/log/xray
chown -R nobody:nogroup /var/log/xray

# --- 校验 + 启动 ------------------------------------------------------------
if ! xray run -test -c "$XRAY_CONF" >/dev/null 2>&1; then
  echo "❌ 配置校验失败，请检查 $XRAY_CONF"; exit 1
fi
echo "✅ 配置校验通过"
systemctl enable xray >/dev/null 2>&1 || true
systemctl restart xray
sleep 1
systemctl is-active xray >/dev/null && echo "✅ xray 服务运行中"

# --- 云安全组提示 -----------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ VLESS+Reality 服务端部署完成"
echo "  UUID      : $UUID"
echo "  PublicKey : $PUB_KEY        (客户端 reality pbk)"
echo "  shortId   : $SHORT_ID"
echo "  dest/SNI  : $DEST"
echo "  端口      : TCP $PORT"
echo "  监听      : $(ss -tln | grep -c ":$PORT" >/dev/null && echo "ss -tlnp | grep ':$PORT' 查看")"
echo "───────────────────────────────────────────────────────"
echo "⚠️  若端口 < 1024，确认安全组放行 TCP $PORT 入站"
echo "⚠️  重要：dest 请选对 TLS 握手宽容的站点（见 SKILL 注意事项，"
echo "    不要用 www.microsoft.com —— Akamai 会拒绝 Reality 握手）"
echo "═══════════════════════════════════════════════════════"
