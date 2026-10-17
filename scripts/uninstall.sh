#!/usr/bin/env bash
# Stop and remove the QQ Agent RollPig adapter.
#
# Default: remove service + plugin, keep sidecar dir and user data.
# --purge: also remove sidecar dir and generated help image (user data is kept).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QQA_HOME="${QQA_HOME:-/opt/qq-agent}"
APP_DIR="$QQA_HOME/app"
SERVICE_DIR="$QQA_HOME/rollpig-service"
MEDIA_DIR="$QQA_HOME/media"
PLUGIN_DIR="$APP_DIR/plugins/rollpig"
BACKUP_DIR="$APP_DIR/data/rollpig-backups"
SERVICE_FILE="/etc/systemd/system/rollpig-sidecar.service"
PURGE=0

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    -h|--help)
      echo "用法: sudo ./scripts/uninstall.sh [--purge]"
      exit 0
      ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;36m[rollpig]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[rollpig] WARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[rollpig] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 或 sudo 运行：sudo ./scripts/uninstall.sh"

if systemctl list-unit-files rollpig-sidecar.service >/dev/null 2>&1; then
  log "停止并禁用 rollpig-sidecar"
  systemctl disable --now rollpig-sidecar >/dev/null 2>&1 || true
fi

if [ -f "$SERVICE_FILE" ]; then
  log "删除服务文件 $SERVICE_FILE"
  rm -f "$SERVICE_FILE"
  systemctl daemon-reload
fi

if [ -d "$PLUGIN_DIR" ]; then
  mkdir -p "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/rollpig-uninstalled-$(date +%Y%m%d-%H%M%S)"
  log "插件目录移到 $BACKUP（不直接删除）"
  mv "$PLUGIN_DIR" "$BACKUP"
fi

if [ "$PURGE" -eq 1 ]; then
  if [ -d "$SERVICE_DIR" ]; then
    log "删除侧车目录 $SERVICE_DIR"
    rm -rf -- "$SERVICE_DIR"
  fi
  if [ -d "$MEDIA_DIR/rollpig/help" ]; then
    log "删除帮助图目录 $MEDIA_DIR/rollpig/help"
    rm -rf -- "$MEDIA_DIR/rollpig/help"
  fi
else
  warn "保留侧车目录 $SERVICE_DIR（如需删除：--purge）"
fi

cat <<EOF

============================================================
卸载完成。

默认保留：
  $SERVICE_DIR
  /root/.local/share/nonebot2/nonebot_plugin_rollpig_plus
  $BACKUP_DIR

如果确认不再需要数据，请手动备份后删除上面的数据目录。
============================================================
EOF
