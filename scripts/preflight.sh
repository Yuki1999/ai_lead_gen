#!/usr/bin/env bash
# 环境预检 —— 部署前在目标服务器上跑，确认环境达标再安装。
#   用法: ./scripts/preflight.sh [前端端口] [后端端口]
# 退出码非 0 表示有硬性条件不满足，请先处理再安装。

set -u
FRONT_PORT="${1:-5173}"
BACK_PORT="${2:-8000}"
fail=0
warn=0

ok()   { printf '  ✓ %s\n' "$1"; }
bad()  { printf '  ✗ %s\n' "$1"; fail=1; }
note() { printf '  ! %s\n' "$1"; warn=1; }

echo "========== 环境预检 =========="

# 操作系统 / 架构
echo "[系统]"
if [ -f /etc/os-release ]; then
  . /etc/os-release 2>/dev/null
  ok "操作系统: ${PRETTY_NAME:-未知}"
else
  note "无 /etc/os-release（非 Linux？生产请部署在 Linux 服务器）"
fi
ARCH="$(uname -m)"
ok "架构: $ARCH"
case "$ARCH" in
  x86_64|amd64) ;;
  aarch64|arm64) note "ARM 架构：请确认交付镜像为 arm64 版本（信创/鲲鹏环境）" ;;
  *) note "少见架构 $ARCH，需确认镜像兼容性" ;;
esac

# Docker
echo "[Docker]"
if command -v docker >/dev/null 2>&1; then
  ok "已安装 docker: $(docker --version 2>/dev/null | sed 's/,.*//')"
  if docker info >/dev/null 2>&1; then
    ok "Docker 守护进程运行中"
  else
    bad "Docker 已装但守护进程未运行（或当前用户无权限，试试 sudo / 加入 docker 组）"
  fi
else
  bad "未安装 Docker —— 离线环境请先用厂商提供的 Docker 离线包安装"
fi

# Docker Compose v2
echo "[Compose]"
if docker compose version >/dev/null 2>&1; then
  ok "已安装 Docker Compose v2: $(docker compose version --short 2>/dev/null)"
elif command -v docker-compose >/dev/null 2>&1; then
  note "只有旧版 docker-compose v1，建议升级到 v2（docker compose）"
else
  bad "未安装 Docker Compose v2"
fi

# 端口占用
echo "[端口]"
check_port() {
  local p="$1" name="$2"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$" && { bad "$name 端口 $p 已被占用"; return; }
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && { bad "$name 端口 $p 已被占用"; return; }
  fi
  ok "$name 端口 $p 空闲"
}
check_port "$FRONT_PORT" "前端"
check_port "$BACK_PORT" "后端"

# 资源：磁盘 / 内存
echo "[资源]"
avail_kb="$(df -Pk . 2>/dev/null | awk 'NR==2{print $4}')"
if [ -n "${avail_kb:-}" ]; then
  avail_gb=$(( avail_kb / 1024 / 1024 ))
  if [ "$avail_gb" -ge 5 ]; then ok "可用磁盘: ${avail_gb}G"; else bad "可用磁盘仅 ${avail_gb}G（建议 ≥5G：镜像约 1-2G + 数据）"; fi
fi
mem_kb="$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null)"
if [ -n "${mem_kb:-}" ]; then
  mem_gb=$(( mem_kb / 1024 / 1024 ))
  if [ "$mem_gb" -ge 2 ]; then ok "内存: ${mem_gb}G"; else note "内存仅 ${mem_gb}G（建议 ≥2G）"; fi
fi

echo "=============================="
if [ "$fail" -ne 0 ]; then
  echo "❌ 预检未通过 —— 请先解决上面标 ✗ 的项再安装"
  exit 1
elif [ "$warn" -ne 0 ]; then
  echo "⚠️ 预检通过，但有提醒项（标 !），请确认无碍后继续"
  exit 0
else
  echo "✅ 预检全部通过，可以安装"
  exit 0
fi
