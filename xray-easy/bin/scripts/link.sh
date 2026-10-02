#!/usr/bin/env bash
# =============================================================================
# xray-easy :: 生成 VLESS 客户端链接
# 用法: sudo ./link.sh <公网IP或域名> [--qr]
# 例  : sudo ./link.sh 43.110.43.207
#       sudo ./link.sh vpn.example.com --qr      # 同时生成二维码 PNG
# 输出: vless://...（v2rayNG 可复制导入 / 扫码）
# =============================================================================
set -euo pipefail

ENDPOINT="${1:-}"
[ -n "$ENDPOINT" ] || { echo "用法: $0 <公网IP或域名> [--qr]"; exit 1; }
QR=0
[ "${2:-}" = "--qr" ] && QR=1

XRAY_CONF=/usr/local/etc/xray/config.json
[ -f "$XRAY_CONF" ] || { echo "❌ 未找到 $XRAY_CONF，请先 install"; exit 1; }

# 读取服务端配置
read -r UUID PORT DEST SID PRIV <<<$(python3 - "$XRAY_CONF" <<'EOF'
import json,sys
c=json.load(open(sys.argv[1]))
rs=c['inbounds'][0]['streamSettings']['realitySettings']
print(c['inbounds'][0]['settings']['clients'][0]['id'],
      c['inbounds'][0]['port'], rs['dest'], rs['shortIds'][0], rs['privateKey'])
EOF
)
SNI="${DEST%%:*}"
PUB=$(xray x25519 -i "$PRIV" | sed -n 's/^Password (PublicKey): //p')

LINK="vless://${UUID}@${ENDPOINT}:${PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=${SNI}&fp=chrome&pbk=${PUB}&sid=${SID}&type=tcp&headerType=none#xray-easy"
echo "$LINK"

if [ "$QR" = 1 ]; then
  OUT=/root/xray-clients/vless-$(date +%H%M%S).png
  mkdir -p /root/xray-clients
  if command -v qrencode >/dev/null 2>&1; then
    echo "$LINK" | qrencode -t PNG -o "$OUT"
  elif python3 -c "import qrcode" 2>/dev/null; then
    python3 - "$OUT" <<EOF
import sys,qrcode
qrcode.QRCode(border=2).add_data("$LINK"); qrcode.QRCode(border=2).make(fit=True)
img=qrcode.make("$LINK"); img.save(sys.argv[1])
EOF
  else
    echo "⚠️  无 qrencode/qrcode，跳过二维码（可 pip install qrcode pillow 后重试）"
    exit 0
  fi
  echo "二维码已生成: $OUT"
fi
