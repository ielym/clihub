#!/usr/bin/env bash
# =============================================================================
# xray-easy :: 更换 Reality 伪装站点（dest / SNI）
# 用法: sudo ./change-dest.sh <站点[:端口]>
# 例  : sudo ./change-dest.sh www.cloudflare.com:443
#       sudo ./change-dest.sh www.apple.com
# 注意: 更换后客户端链接中的 sni 需同步更新，请重新生成链接/二维码
# =============================================================================
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }

DEST="${1:-}"
[ -n "$DEST" ] || { echo "用法: $0 <站点[:端口]>"; exit 1; }
[[ "$DEST" == *:* ]] || DEST="$DEST:443"
SNI="${DEST%%:*}"

XRAY_CONF=/usr/local/etc/xray/config.json
[ -f "$XRAY_CONF" ] || { echo "❌ 未找到 $XRAY_CONF，请先 install"; exit 1; }

# 换 dest 前先验证该站点 TLS 可达（避免本次排查中微软 Akamai 拒绝握手的坑）
if ! curl -s --max-time 8 -o /dev/null "https://$DEST"; then
  echo "⚠️  $DEST 当前 TLS 不可达，仍继续（Reality 需要服务器能访问该站点完成伪装握手）"
fi

python3 - "$XRAY_CONF" "$DEST" "$SNI" <<'EOF'
import json,sys
conf,dest,sni=sys.argv[1:4]
c=json.load(open(conf))
rs=c['inbounds'][0]['streamSettings']['realitySettings']
rs['dest']=dest
rs['serverNames']=[sni]
json.dump(c,open(conf,'w'),indent=2)
print(f"dest 已改为 {dest}, serverNames=[{sni}]")
EOF

xray run -test -c "$XRAY_CONF" >/dev/null 2>&1 || { echo "❌ 配置校验失败"; exit 1; }
systemctl restart xray && sleep 1
systemctl is-active xray >/dev/null && echo "✅ xray 已重启"

echo ""
echo "⚠️  客户端链接中的 sni 参数必须同步为: $SNI"
echo "   请重新运行 xray-easy link <公网IP或域名> 生成新链接并重新导入手机"
