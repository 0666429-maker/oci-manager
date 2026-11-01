#!/usr/bin/env bash
# oci-manager 一键安装脚本（对标原 R-Bot 的 releases 下载安装方式）。
#
# 前提：你已经把本仓库推到 GitHub，并且打了一个 vX.Y.Z 的 tag，
# GitHub Actions 会自动把 oci-manager.zip 挂到那个 Release 上。
#
# 用法（在 Ubuntu VPS 上执行，把 <你的GitHub用户名> 换成你自己的）：
#   wget -O install.sh https://raw.githubusercontent.com/<你的GitHub用户名>/oci-manager/main/install.sh
#   bash install.sh <你的GitHub用户名> --systemd
#
# 也可以用完整仓库名：
#   bash install.sh <你的GitHub用户名>/oci-manager --systemd
#
# 之后只要填 .env 里的 OCI 密钥就能跑，详见 README 的“Ubuntu VPS 部署”。
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "用法：bash install.sh <你的GitHub用户名> [--systemd] [--bot] [--monitor]" >&2
  echo "示例：bash install.sh octocat --systemd" >&2
  exit 1
fi

ARG="$1"; shift
if [[ "$ARG" == */* ]]; then
  REPO="$ARG"
else
  REPO="$ARG/oci-manager"
fi

URL="https://github.com/$REPO/releases/latest/download/oci-manager.zip"
TMP_ZIP="$(mktemp /tmp/oci-manager-XXXXXX.zip)"
echo "==> 从 $URL 下载最新 Release"
if command -v curl >/dev/null 2>&1; then
  curl -L --fail -o "$TMP_ZIP" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$TMP_ZIP" "$URL"
else
  echo "需要 curl 或 wget，请先安装一个。" >&2
  exit 1
fi

echo "==> 解压到 ~/oci-manager（已有 .env 会先备份、解压后恢复）"
ENV_BACKUP=""
if [ -f "$HOME/oci-manager/.env" ]; then
  ENV_BACKUP="$(mktemp /tmp/oci-manager-env-XXXXXX)"
  cp "$HOME/oci-manager/.env" "$ENV_BACKUP"
fi
mkdir -p "$HOME/oci-manager"
unzip -o -q "$TMP_ZIP" -d "$HOME"
rm -f "$TMP_ZIP"
if [ -n "$ENV_BACKUP" ]; then
  cp "$ENV_BACKUP" "$HOME/oci-manager/.env"
  rm -f "$ENV_BACKUP"
fi

cd "$HOME/oci-manager"
echo "==> 运行 Ubuntu 安装脚本"
bash scripts/install-ubuntu.sh "$@"
echo "==> 完成。下一步：nano .env 填 OCI 密钥，然后 .venv/bin/python run.py 试跑。"
