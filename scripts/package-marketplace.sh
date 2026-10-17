#!/usr/bin/env bash
# Build the QQA marketplace zip from plugin/.
#
# The zip contains plugin.json, index.js, assets/rollpig-help.png, and INSTALL.md
# at its root.
# It deliberately does NOT contain the Python sidecar (marketplace limit is
# 32 MB unpacked and the sidecar needs systemd/Python, which the marketplace
# cannot install).
#
# Usage: ./scripts/package-marketplace.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/dist/rollpig-marketplace.zip"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log()  { printf '\033[1;36m[rollpig]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[rollpig] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "找不到 $PYTHON_BIN"

mkdir -p "$ROOT/dist"
rm -f "$OUT"

"$PYTHON_BIN" - "$ROOT" "$OUT" <<'PY'
import json
import os
import sys
import zipfile

root, out = sys.argv[1], sys.argv[2]
plugin_dir = os.path.join(root, "plugin")
plugin_json = os.path.join(plugin_dir, "plugin.json")
index_js = os.path.join(plugin_dir, "index.js")
help_png = os.path.join(plugin_dir, "assets", "rollpig-help.png")
install_md = os.path.join(root, "docs", "marketplace-install.md")

for path in (plugin_json, index_js, help_png, install_md):
    if not os.path.isfile(path):
        raise SystemExit(f"missing required file: {path}")

raw = open(plugin_json, "rb").read()
if raw.startswith(b"\xef\xbb\xbf"):
    raise SystemExit("plugin.json has a UTF-8 BOM; QQA requires UTF-8 without BOM")
try:
    manifest = json.loads(raw.decode("utf-8"))
except Exception as exc:
    raise SystemExit(f"plugin.json is not valid UTF-8 JSON: {exc}")

if not manifest.get("id"):
    raise SystemExit("plugin.json has no id")
if manifest.get("apiVersion") != 1:
    raise SystemExit("plugin.json apiVersion must be 1")

entries = [
    ("plugin.json", raw),
    ("index.js", open(index_js, "rb").read()),
    ("assets/rollpig-help.png", open(help_png, "rb").read()),
    ("INSTALL.md", open(install_md, "rb").read()),
]

with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for name, data in entries:
        zf.writestr(name, data)

size = os.path.getsize(out)
if size > 8 * 1024 * 1024:
    raise SystemExit(f"zip is too large: {size} bytes > 8 MiB")
if len(entries) > 100:
    raise SystemExit(f"too many files: {len(entries)} > 100")

print(f"id={manifest['id']} version={manifest.get('version')}")
print(f"files={len(entries)} zip_bytes={size}")
print(f"output={out}")
PY

log "已生成 $OUT"
log "上传前请确认：市场页必须显著说明“需要先安装同机侧车”，并链接 GitHub 仓库。"
