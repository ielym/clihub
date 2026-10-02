#!/usr/bin/env bash
# wireguard-easy :: 移除客户端
# 用法: sudo ./remove-client.sh <设备名或公钥>
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "❌ 请用 root 运行"; exit 1; }
TARGET="${1:?用法: sudo ./remove-client.sh <设备名或公钥>}"

# 从 /root/wireguard-clients/<name>.pub 反查公钥
if [ -f "/root/wireguard-clients/${TARGET}.pub" ]; then
  PUB=$(cat "/root/wireguard-clients/${TARGET}.pub")
elif echo "$TARGET" | grep -q '='; then
  PUB="$TARGET"
else
  echo "❌ 找不到设备 ${TARGET}，请提供 /root/wireguard-clients 中的名称或公钥"; exit 1
fi

# 热移除
wg set wg0 peer "$PUB" remove

# 从 wg0.conf 移除对应 [Peer] 块（按块过滤，保证幂等与安全）
python3 - "$PUB" /etc/wireguard/wg0.conf <<'PYEOF'
import sys
pub, path = sys.argv[1], sys.argv[2]
lines = open(path).read().split('\n')
out, i = [], 0
while i < len(lines):
    if lines[i].strip() == '[Peer]':
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith('['):
            j += 1
        block = lines[i:j]
        if any(pub in ln for ln in block):
            i = j
            continue
        out.extend(block)
        i = j
    else:
        out.append(lines[i])
        i += 1
open(path, 'w').write('\n'.join(out))
PYEOF
chmod 600 /etc/wireguard/wg0.conf

# 清理客户端文件
rm -f "/root/wireguard-clients/${TARGET}.conf" \
      "/root/wireguard-clients/${TARGET}.key" \
      "/root/wireguard-clients/${TARGET}.pub" \
      "/root/wireguard-clients/${TARGET}.png"
echo "✅ 已移除 peer ${TARGET}（含热配置、持久化条目与客户端文件）"
