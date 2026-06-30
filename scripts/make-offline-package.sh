#!/usr/bin/env bash
# 制作私有化离线交付包 —— 在【有网的构建机】上运行。
#   用法: ./scripts/make-offline-package.sh [版本号]
#   示例: ./scripts/make-offline-package.sh 1.0.0
#   不传版本号则用 日期+git短SHA。
#
# 产物: dist/ai_lead_gen-offline-<版本>.tar.gz
#   里面含：三个服务镜像(tar)、离线 compose、.env 模板、安装/预检/冒烟脚本、
#          交付清单 MANIFEST、校验和 SHA256SUMS、安装手册。
# 客户现场断网即可: 解压 → ./install-offline.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
VERSION="${1:-$(date +%Y%m%d)-${GIT_SHA}}"
NAME="ai_lead_gen"
STAGE="dist/${NAME}-offline-${VERSION}"
IMAGES=("medbot-backend:${VERSION}" "medbot-agent:${VERSION}" "medbot-frontend:${VERSION}")

echo "==> 构建版本: ${VERSION}"
command -v docker >/dev/null || { echo "需要 docker"; exit 1; }

echo "==> [1/4] 构建镜像"
docker build -t "medbot-backend:${VERSION}"  -f backend/Dockerfile  .
docker build -t "medbot-agent:${VERSION}"    -f agent/Dockerfile    .
docker build -t "medbot-frontend:${VERSION}" -f frontend/Dockerfile --build-arg VITE_API_BASE_URL=/api .

echo "==> [2/4] 组织交付目录: ${STAGE}"
rm -rf "$STAGE"
mkdir -p "$STAGE/agent"
cp docker-compose.deploy.yml "$STAGE/"
cp scripts/preflight.sh scripts/smoke-test.sh scripts/install-offline.sh "$STAGE/"
chmod +x "$STAGE"/*.sh
[ -f docs/DEPLOY.md ] && cp docs/DEPLOY.md "$STAGE/安装手册.md" || true
cp agent/.env.example "$STAGE/agent/.env.example"

# 现场用的 .env 模板（密钥留空，IMAGE_TAG 已填好）
cat > "$STAGE/.env" <<EOF
# ===== 部署配置（现场按需修改）=====
IMAGE_TAG=${VERSION}
FRONTEND_PORT=5173
BACKEND_PORT=8000
PUBLIC_ORIGIN=http://localhost:5173
# 后端调用 Agent 的内部令牌（安装脚本会自动生成，无需手填）
MEDBOT_SERVICE_TOKEN=
EOF

echo "==> [3/4] 导出镜像 (docker save + gzip)"
docker save "${IMAGES[@]}" | gzip > "$STAGE/images.tar.gz"

# 交付清单
cat > "$STAGE/MANIFEST.txt" <<EOF
产品:     微创畅行 海外渠道拓展系统 (ai_lead_gen)
版本:     ${VERSION}
构建时间: $(date '+%Y-%m-%d %H:%M:%S %z')
GIT提交:  ${GIT_SHA}
镜像清单:
  - ${IMAGES[0]}
  - ${IMAGES[1]}
  - ${IMAGES[2]}
镜像标签: IMAGE_TAG=${VERSION}
安装方式: 解压后执行 ./install-offline.sh
EOF

echo "==> [4/4] 生成校验和 + 打包"
( cd "$STAGE" && find . -type f ! -name SHA256SUMS -exec shasum -a 256 {} \; > SHA256SUMS )
( cd dist && tar czf "${NAME}-offline-${VERSION}.tar.gz" "${NAME}-offline-${VERSION}" )

PKG="dist/${NAME}-offline-${VERSION}.tar.gz"
echo
echo "✅ 完成: ${PKG}"
echo "   大小: $(du -h "$PKG" | awk '{print $1}')"
echo "   校验: $(shasum -a 256 "$PKG" | awk '{print $1}')"
echo
echo "交付给客户：把 ${PKG} 拷到目标服务器 → 解压 → ./install-offline.sh"
