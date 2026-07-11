#!/bin/bash
# 安装 ym-ocr 为 systemd 用户服务并设为登录/开机自启（无需 sudo）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/deploy/ym-ocr.user.service"
UNIT_DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/ym-ocr.service"

if [[ ! -f "$ROOT/.venv/bin/python3" ]]; then
  echo "缺少虚拟环境，请先执行: cd $ROOT && uv sync"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "缺少 .env，请先复制: cp $ROOT/.env.example $ROOT/.env"
  exit 1
fi

mkdir -p "$(dirname "$UNIT_DST")"
# 展开 %h 为实际 home（systemd 会在运行时展开，此处写入绝对路径更直观）
sed "s|%h|$HOME|g" "$UNIT_SRC" > "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable ym-ocr.service
systemctl --user restart ym-ocr.service

# WSL/无图形登录时，允许用户服务在未登录时自启
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

echo ""
echo "状态:"
systemctl --user status ym-ocr.service --no-pager -l || true
echo ""
echo "常用命令:"
echo "  systemctl --user status ym-ocr"
echo "  systemctl --user restart ym-ocr"
echo "  journalctl --user -u ym-ocr -f"
