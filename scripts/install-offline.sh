#!/usr/bin/env bash
# 离线安装 —— 在【客户服务器】上、解压交付包后运行。全程无需外网。
#   用法: ./install-offline.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

COMPOSE="docker-compose.deploy.yml"
echo "================ 离线安装 ================"
[ -f MANIFEST.txt ] && { echo "[交付清单]"; cat MANIFEST.txt; echo; }

# 读取端口（供预检/冒烟用）
FRONT_PORT="$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2)"; FRONT_PORT="${FRONT_PORT:-5173}"
BACK_PORT="$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2)";  BACK_PORT="${BACK_PORT:-8000}"

echo "==> [1/6] 环境预检"
./preflight.sh "$FRONT_PORT" "$BACK_PORT"

echo "==> [2/6] 校验交付包完整性"
if command -v shasum >/dev/null 2>&1; then
  shasum -a 256 -c SHA256SUMS >/dev/null && echo "  ✓ 校验和通过" || { echo "  ✗ 文件校验失败，交付包可能损坏，请重新拷贝"; exit 1; }
else
  echo "  ! 无 shasum，跳过校验（建议手工核对 MANIFEST 中的镜像）"
fi

echo "==> [3/6] 导入镜像 (docker load)"
gzip -dc images.tar.gz | docker load

echo "==> [4/6] 准备配置"
# Agent 配置（LLM key 等）—— 现场填写
if [ ! -f agent/.env ]; then
  cp agent/.env.example agent/.env
  echo "  · 已生成 agent/.env（请填写 OPENAI_API_KEY 或 DASHSCOPE_API_KEY 等，否则 AI 功能不可用）"
fi
# 自动生成并同步后端<->Agent 内部令牌
gen_token() { if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32; else head -c32 /dev/urandom | od -An -tx1 | tr -d ' \n'; fi; }
TOKEN="$(grep -E '^MEDBOT_SERVICE_TOKEN=' .env | cut -d= -f2)"
if [ -z "$TOKEN" ]; then
  TOKEN="$(gen_token)"
  # 写回 .env
  if grep -qE '^MEDBOT_SERVICE_TOKEN=' .env; then
    sed -i.bak "s|^MEDBOT_SERVICE_TOKEN=.*|MEDBOT_SERVICE_TOKEN=${TOKEN}|" .env && rm -f .env.bak
  else
    echo "MEDBOT_SERVICE_TOKEN=${TOKEN}" >> .env
  fi
  echo "  · 已生成内部服务令牌 MEDBOT_SERVICE_TOKEN"
fi
# 同步到 agent/.env 的 BACKEND_SERVICE_TOKEN
if grep -qE '^BACKEND_SERVICE_TOKEN=' agent/.env; then
  sed -i.bak "s|^BACKEND_SERVICE_TOKEN=.*|BACKEND_SERVICE_TOKEN=${TOKEN}|" agent/.env && rm -f agent/.env.bak
else
  echo "BACKEND_SERVICE_TOKEN=${TOKEN}" >> agent/.env
fi

echo "==> [5/6] 启动服务"
docker compose -f "$COMPOSE" up -d

echo "==> [6/6] 冒烟测试"
./smoke-test.sh "$FRONT_PORT" "$BACK_PORT" || {
  echo "提示：若刚启动可稍等 1-2 分钟后重试 ./smoke-test.sh ${FRONT_PORT} ${BACK_PORT}"
}

echo
echo "================ 安装完成 ================"
echo "Web 访问:      http://<本机IP>:${FRONT_PORT}"
echo "后端健康检查:  http://<本机IP>:${BACK_PORT}/health"
echo "默认管理员:    admin / admin123  （首次登录强制改密）"
echo "常用运维:"
echo "  查看状态: docker compose -f ${COMPOSE} ps"
echo "  看日志:   docker compose -f ${COMPOSE} logs -f"
echo "  停止:     docker compose -f ${COMPOSE} down"
