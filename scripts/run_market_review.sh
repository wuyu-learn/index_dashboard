#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/data/metadata"
LOG_FILE="${LOG_DIR}/market-review.log"
LOCK_FILE="${LOG_DIR}/market-review.lock"

mkdir -p "${LOG_DIR}"

# cron 的 PATH 通常很精简；mmx-cli 常安装在这些目录。
export PATH="/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:${HOME}/.local/bin:${PATH:-}"

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "未找到 Python 3" >&2
  exit 1
fi

if ! command -v mmx >/dev/null 2>&1; then
  echo "未找到 mmx，请先执行：npm install -g mmx-cli" >&2
  exit 1
fi

run_collector() {
  cd "${PROJECT_ROOT}"
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] 开始采集财联社收评"
  "${PYTHON_BIN}" -m backend.news.runner
  echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] 收评采集完成"
}

if command -v flock >/dev/null 2>&1; then
  (
    if ! flock -n 9; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S %z')] 已有收评采集任务运行，跳过"
      exit 0
    fi
    run_collector
  ) 9>"${LOCK_FILE}" >>"${LOG_FILE}" 2>&1
else
  # macOS 默认没有 flock；本地调试仍可运行，服务器建议安装 util-linux。
  run_collector >>"${LOG_FILE}" 2>&1
fi
