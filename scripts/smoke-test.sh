#!/usr/bin/env bash
# 冒烟测试 —— 部署后跑，确认关键链路真的可用，再把系统交给客户。
#   用法: ./scripts/smoke-test.sh [前端端口] [后端端口]
set -u
FRONT_PORT="${1:-5173}"
BACK_PORT="${2:-8000}"
BACK="http://127.0.0.1:${BACK_PORT}"
FRONT="http://127.0.0.1:${FRONT_PORT}"
fail=0

ok()  { printf '  ✓ %s\n' "$1"; }
bad() { printf '  ✗ %s\n' "$1"; fail=1; }

# 等待后端健康（最多 ~60s，覆盖容器启动时间）
echo "[等待服务就绪]"
for i in $(seq 1 30); do
  if curl -fs --noproxy '*' "${BACK}/health" >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "[关键链路检查]"
# 1) 后端健康
if curl -fs --noproxy '*' "${BACK}/health" | grep -q '"ok"'; then
  ok "后端 /health 正常"
else
  bad "后端 /health 异常（${BACK}/health）"
fi

# 2) 前端可访问
code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' "${FRONT}/" 2>/dev/null)"
if [ "$code" = "200" ]; then ok "前端首页可访问 (HTTP 200)"; else bad "前端首页异常 (HTTP ${code:-超时})"; fi

# 3) 前端 → 后端 同源反代 /api 通
code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' "${FRONT}/api/health" 2>/dev/null)"
if [ "$code" = "200" ]; then ok "前端 /api 反代到后端正常"; else bad "前端 /api 反代异常 (HTTP ${code:-超时})"; fi

# 4) 鉴权链路：默认管理员能登录
login_code="$(curl -s --noproxy '*' -o /dev/null -w '%{http_code}' -X POST "${BACK}/auth/login" \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' 2>/dev/null)"
if [ "$login_code" = "200" ]; then
  ok "鉴权链路正常（默认管理员可登录 —— 请提醒客户首次登录后立即改密）"
else
  bad "登录接口异常 (HTTP ${login_code:-超时})"
fi

echo "=============================="
if [ "$fail" -eq 0 ]; then
  echo "✅ 冒烟测试通过 —— 系统可用，可交付客户"
  exit 0
else
  echo "❌ 冒烟测试未通过 —— 请查看容器日志: docker compose -f docker-compose.deploy.yml logs"
  exit 1
fi
