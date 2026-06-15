#!/usr/bin/env bash
# Quick setup for cloud server without Docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Medbot Setup ==="

# 1. Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "Need python3"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Need node.js"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Need npm"; exit 1; }

# 2. Install backend deps
echo "Installing backend dependencies..."
cd backend
python3 -m pip install uv --quiet 2>/dev/null || python3 -m pip install uv 2>/dev/null
uv sync 2>&1 | tail -3
cd ..

# 3. Install frontend deps
echo "Installing frontend dependencies..."
cd frontend
npm install --silent 2>&1 | tail -3
cd ..

# 4. Install agent deps
echo "Installing agent dependencies..."
cd agent
npm install --silent 2>&1 | tail -3
cd ..

# 5. Setup .env
if [ ! -f .env ]; then
  cp .env.deploy.example .env
  echo "Created .env from .env.deploy.example"
fi
if [ ! -f agent/.env ]; then
  cp agent/.env.example agent/.env
  echo "Created agent/.env from agent/.env.example"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start:"
echo "  Terminal 1: cd agent && AGENT_HOST=0.0.0.0 AGENT_PORT=8011 BACKEND_BASE_URL=http://localhost:8000 npx tsx index.ts"
echo "  Terminal 2: cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "  Terminal 3: cd frontend && npx vite --host 0.0.0.0 --port 5173"
echo ""
echo "Or use docker-compose: docker compose up -d"
