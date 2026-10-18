#!/bin/sh
# P0 兼容入口；统一构建逻辑位于 tools/build.py。
set -e
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" tools/build.py run --stage p0 "$@"
