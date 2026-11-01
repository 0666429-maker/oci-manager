#!/usr/bin/env bash
# Ubuntu VPS 一键安装 oci-manager（不含 OCI 密钥配置，密钥仍需你手动填 .env）。
#
# 用法（在项目根目录 oci-manager 里执行）：
#   bash scripts/install-ubuntu.sh                # 只装依赖 + 建 venv，不设开机自启
#   bash scripts/install-ubuntu.sh --systemd      # 再加 systemd 开机自启
#   bash scripts/install-ubuntu.sh --systemd --bot --monitor
#                                               # 自启时同时启动 Telegram Bot 和监控
#
# 注意：脚本不会覆盖已有的 .env；第一次运行后请手动编辑 .env 填 OCI 密钥。
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
USER_NAME="$(id -un)"
HOME_DIR="$HOME"

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

SYSTEMD=0
EXTRA_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --systemd) SYSTEMD=1 ;;
    --bot) EXTRA_ARGS+=("--bot") ;;
    --monitor) EXTRA_ARGS+=("--monitor") ;;
    *) echo "未知参数：$arg" >&2; exit 1 ;;
  esac
done

echo "==> 1. 安装系统依赖（python3 / venv / unzip）"
if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update
  $SUDO apt-get install -y python3 python3-venv unzip
else
  echo "未找到 apt-get，请手动安装 python3、python3-venv、unzip 后再运行本脚本。" >&2
  exit 1
fi

echo "==> 2. 创建虚拟环境并安装 Python 依赖"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "==> 3. 生成配置文件（已有 .env 则不覆盖）"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "已生成 .env，请用 nano .env 填好 OCI 密钥和面板账号后再启动。"
else
  echo ".env 已存在，未覆盖。"
fi

if [ "$SYSTEMD" -eq 1 ]; then
  echo "==> 4. 安装 systemd 开机自启服务"
  SERVICE_FILE="/etc/systemd/system/oci-manager.service"
  TMP_FILE="$(mktemp)"
  sed -e "s|__USER__|$USER_NAME|g" \
      -e "s|__WORKDIR__|$PROJECT_DIR|g" \
      -e "s|__EXTRA_ARGS__|${EXTRA_ARGS[*]:-}|g" \
      scripts/oci-manager.service > "$TMP_FILE"
  $SUDO cp "$TMP_FILE" "$SERVICE_FILE"
  rm -f "$TMP_FILE"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now oci-manager
  $SUDO systemctl status oci-manager --no-pager || true
  echo "systemd 服务已启动，查看日志：sudo journalctl -u oci-manager -f"
else
  echo "==> 完成。先手动试跑一次（能看到日志、无报错再设自启）："
  echo "    .venv/bin/python run.py ${EXTRA_ARGS[*]:-}"
  echo "  另开一个终端验证：curl http://127.0.0.1:9527/api/health"
fi
