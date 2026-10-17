#!/usr/bin/env bash
# Install the QQ Agent RollPig adapter and its Python sidecar.
#
# Usage:
#   sudo ./scripts/install.sh
#   sudo QQA_HOME=/path/to/qq-agent ./scripts/install.sh
#
# The script is intentionally idempotent: it keeps an existing
# rollpig_config.json and moves the old plugin directory to a backup outside
# plugins/ (the QQA loader scans every top-level directory under plugins/).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QQA_HOME="${QQA_HOME:-/opt/qq-agent}"
APP_DIR="$QQA_HOME/app"
SERVICE_DIR="$QQA_HOME/rollpig-service"
MEDIA_DIR="${QQA_MEDIA_DIR:-$QQA_HOME/media}"
PLUGIN_DIR="$APP_DIR/plugins/rollpig"
BACKUP_DIR="$APP_DIR/data/rollpig-backups"
SERVICE_FILE="/etc/systemd/system/rollpig-sidecar.service"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEPLOY_MODE="${QQA_DEPLOY_MODE:-auto}"
CONTAINER_NAME="${QQA_CONTAINER_NAME:-qq-agent}"

log()  { printf '\033[1;36m[rollpig]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[rollpig] WARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[rollpig] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 或 sudo 运行：sudo ./scripts/install.sh"
command -v systemctl >/dev/null 2>&1 || die "没有 systemd（systemctl），本安装脚本不支持当前系统"
[ -d "$APP_DIR" ] || die "找不到 QQA 目录：$APP_DIR（可用 QQA_HOME=... 指定）"
[ -d "$APP_DIR/plugins" ] || die "找不到插件目录：$APP_DIR/plugins"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "找不到 $PYTHON_BIN"

# Docker：宿主 media 目录被挂进 qq-agent 的 /media，侧车要返回 /media/...
# 原生：侧车和 QQA 在同一台机器，返回绝对路径，QQA 直接读。
if [ "$DEPLOY_MODE" = "auto" ]; then
  if command -v docker >/dev/null 2>&1 \
    && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    MOUNT_SOURCE="$(docker inspect -f \
      '{{range .Mounts}}{{if eq .Destination "/media"}}{{.Source}}{{end}}{{end}}' \
      "$CONTAINER_NAME" 2>/dev/null || true)"
    if [ -n "$MOUNT_SOURCE" ]; then
      DEPLOY_MODE="docker"
      # 只有用户没显式指定 QQA_MEDIA_DIR 时才采用容器实际挂载源。
      [ -n "${QQA_MEDIA_DIR:-}" ] || MEDIA_DIR="$MOUNT_SOURCE"
    else
      DEPLOY_MODE="native"
    fi
  else
    DEPLOY_MODE="native"
  fi
fi

case "$DEPLOY_MODE" in
  docker)
    MEDIA_URL_PREFIX="/media"
    ;;
  native)
    MEDIA_URL_PREFIX="$MEDIA_DIR"
    # QQA 进程直接读这个路径；相对路径会随工作目录变化，必须拒绝。
    case "$MEDIA_URL_PREFIX" in
      /*) ;;
      *) die "原生模式的 QQA_MEDIA_DIR 必须是绝对路径，当前：$MEDIA_URL_PREFIX" ;;
    esac
    ;;
  *)
    die "QQA_DEPLOY_MODE 只能是 auto / docker / native，当前：$DEPLOY_MODE"
    ;;
esac

"$PYTHON_BIN" - <<'PY' || die "需要 Python 3.10 或更高版本"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

if ! "$PYTHON_BIN" -c 'import ensurepip' >/dev/null 2>&1; then
  die "当前 Python 缺少 venv/ensurepip。请先运行：sudo apt-get install -y python3-venv python3-pip"
fi

log "QQA_HOME=$QQA_HOME"
log "部署形态=$DEPLOY_MODE，媒体目录=$MEDIA_DIR，发送前缀=$MEDIA_URL_PREFIX"
log "安装侧车到 $SERVICE_DIR"
mkdir -p "$SERVICE_DIR" "$MEDIA_DIR/rollpig/help" "$BACKUP_DIR"
install -m 644 "$ROOT/sidecar/server.py" "$SERVICE_DIR/server.py"
install -m 644 "$ROOT/sidecar/make_help_image.py" "$SERVICE_DIR/make_help_image.py"
install -m 644 "$ROOT/sidecar/requirements.txt" "$SERVICE_DIR/requirements.txt"

if [ -f "$SERVICE_DIR/rollpig_config.json" ]; then
  log "保留已有配置：$SERVICE_DIR/rollpig_config.json"
else
  install -m 600 "$ROOT/sidecar/rollpig_config.example.json" "$SERVICE_DIR/rollpig_config.json"
  log "已生成默认配置：$SERVICE_DIR/rollpig_config.json"
fi

if [ ! -x "$SERVICE_DIR/venv/bin/python" ]; then
  log "创建 venv：$SERVICE_DIR/venv"
  "$PYTHON_BIN" -m venv "$SERVICE_DIR/venv"
fi

PIP_ARGS=()
if [ -n "${PIP_INDEX_URL:-}" ]; then
  PIP_ARGS+=(--index-url "$PIP_INDEX_URL")
fi
if [ -n "${PIP_TRUSTED_HOST:-}" ]; then
  PIP_ARGS+=(--trusted-host "$PIP_TRUSTED_HOST")
fi

log "安装 Python 依赖（首次约 1–3 分钟）"
"$SERVICE_DIR/venv/bin/python" -m pip install "${PIP_ARGS[@]}" --upgrade pip setuptools wheel >/dev/null
"$SERVICE_DIR/venv/bin/pip" install "${PIP_ARGS[@]}" -r "$ROOT/sidecar/requirements.txt"

log "生成小猪帮助图"
if ! ROLLPIG_SERVICE_DIR="$SERVICE_DIR" QQA_MEDIA_DIR="$MEDIA_DIR" \
  "$SERVICE_DIR/venv/bin/python" "$ROOT/sidecar/make_help_image.py"; then
  warn "帮助图生成失败，使用仓库内置图片"
  install -m 644 "$ROOT/plugin/assets/rollpig-help.png" "$MEDIA_DIR/rollpig/help/rollpig-help.png"
fi

if [ -d "$PLUGIN_DIR" ]; then
  BACKUP="$BACKUP_DIR/rollpig-$(date +%Y%m%d-%H%M%S)"
  log "备份旧插件到 $BACKUP"
  mv "$PLUGIN_DIR" "$BACKUP"
fi
mkdir -p "$PLUGIN_DIR/assets"
install -m 644 "$ROOT/plugin/plugin.json" "$PLUGIN_DIR/plugin.json"
install -m 644 "$ROOT/plugin/index.js" "$PLUGIN_DIR/index.js"
install -m 644 "$ROOT/plugin/assets/rollpig-help.png" "$PLUGIN_DIR/assets/rollpig-help.png"
log "插件已写入 $PLUGIN_DIR"

log "写入 systemd 服务：$SERVICE_FILE"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=RollPig sidecar for QQ Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=$SERVICE_DIR
ExecStart=$SERVICE_DIR/venv/bin/python $SERVICE_DIR/server.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment="QQA_HOME=$QQA_HOME"
Environment="QQA_MEDIA_DIR=$MEDIA_DIR"
Environment="QQA_MEDIA_URL_PREFIX=$MEDIA_URL_PREFIX"
Environment="QQA_DEPLOY_MODE=$DEPLOY_MODE"
Environment="ROLLPIG_CONFIG_FILE=$SERVICE_DIR/rollpig_config.json"
Environment="ROLLPIG_PORT=${ROLLPIG_PORT:-18765}"
Environment="TZ=Asia/Shanghai"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rollpig-sidecar >/dev/null
systemctl restart rollpig-sidecar

log "等待侧车健康检查 ..."
HEALTH_URL="http://127.0.0.1:${ROLLPIG_PORT:-18765}/health"
ok=0
for _ in $(seq 1 30); do
  if command -v curl >/dev/null 2>&1 && curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done

if [ "$ok" -eq 1 ]; then
  log "侧车正常：$(curl -fsS "$HEALTH_URL")"
else
  warn "30 秒内未通过健康检查，请查看：journalctl -u rollpig-sidecar -n 100 --no-pager"
fi

# 触发 QQA 热重载（如果 QQA 正在运行）。
touch "$PLUGIN_DIR/index.js" 2>/dev/null || true

cat <<EOF

============================================================
安装完成。
部署形态：$DEPLOY_MODE
媒体目录：$MEDIA_DIR
发送前缀：$MEDIA_URL_PREFIX

检查：
  curl -s $HEALTH_URL
  systemctl status rollpig-sidecar --no-pager
  journalctl -u rollpig-sidecar -n 80 --no-pager

QQ Agent 控制台：
  「插件」页签应出现「今日小猪（RollPig）」
  群里发送：小猪帮助 / 今日小猪

配置：
  $SERVICE_DIR/rollpig_config.json
  修改后：sudo systemctl restart rollpig-sidecar

升级：
  git pull && sudo ./scripts/install.sh

卸载：
  sudo ./scripts/uninstall.sh
============================================================
EOF
