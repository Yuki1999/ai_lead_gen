#!/usr/bin/env bash
# 本地 CI 检查 —— 一条命令跑完所有质量门禁，全绿才放心 push。
#
#   用法:  ./scripts/ci-check.sh
#
# 跑的内容和 .gitlab-ci.yml 一致：后端单元测试 + Agent 构建 + 前端构建。
# 前提：依赖已安装（backend/.venv、agent/node_modules、frontend/node_modules）。
# 它只跑测试/构建、不装依赖，所以快、也不受 npm 镜像网络影响。

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0

run() {
  local name="$1"; shift
  printf '▶ %s ...\n' "$name"
  if ( "$@" ); then
    printf '  ✓ %s 通过\n\n' "$name"
  else
    printf '  ✗ %s 失败\n\n' "$name"
    fail=1
  fi
}

backend_test() {
  cd "$ROOT/backend" || return 1
  if command -v uv >/dev/null 2>&1; then
    uv run pytest -q
  elif [ -x .venv/bin/python ]; then
    .venv/bin/python -m pytest -q
  else
    echo "  未找到 uv 或 backend/.venv，请先安装后端依赖"; return 1
  fi
}

agent_build()    { cd "$ROOT/agent"    && npm run build; }
frontend_build() { cd "$ROOT/frontend" && npm run build; }

echo "================ 本地 CI 检查 ================"
echo
run "后端测试 (pytest)"          backend_test
run "Agent 构建 (tsc)"           agent_build
run "前端构建 (vue-tsc + vite)"  frontend_build

if [ "$fail" -eq 0 ]; then
  echo "✅ 全部通过 —— 可以安心 push 了"
else
  echo "❌ 有检查未通过 —— 请修复后再 push"
fi
exit "$fail"
