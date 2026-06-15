#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

read_env_value() {
  local file="$1"
  local key="$2"
  if [ ! -f "$file" ]; then
    return 0
  fi
  grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'
}

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp

  tmp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { written = 0 }
    $0 ~ "^" key "=" {
      if (!written) {
        print key "=" value
        written = 1
      }
      next
    }
    { print }
    END {
      if (!written) {
        print key "=" value
      }
    }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

generate_agent_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('hex'))"
  fi
}

ensure_shared_agent_token() {
  local root_token
  local agent_token
  local token

  root_token="$(read_env_value .env AGENT_TOKEN)"
  agent_token="$(read_env_value agent/.env AGENT_TOKEN)"
  token="${root_token:-$agent_token}"

  if [ -z "$token" ]; then
    token="$(generate_agent_token)"
    echo "Generated AGENT_TOKEN for backend <-> agent communication"
  fi

  set_env_value .env AGENT_TOKEN "$token"
  set_env_value agent/.env AGENT_TOKEN "$token"
}

sync_agent_container_defaults() {
  local public_origin
  public_origin="$(read_env_value .env PUBLIC_ORIGIN)"

  set_env_value agent/.env BACKEND_BASE_URL "http://backend:8000"
  set_env_value agent/.env AGENT_HOST "0.0.0.0"
  set_env_value agent/.env AGENT_PORT "8011"
  set_env_value agent/.env AGENT_CORS_ORIGIN "${public_origin:-http://localhost:5173}"
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Engine or Docker Desktop first." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required. Install the docker compose plugin first." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.deploy.example .env
  echo "Created .env from .env.deploy.example"
fi

if [ ! -f agent/.env ]; then
  cp agent/.env.example agent/.env
  echo "Created agent/.env from agent/.env.example"
fi

ensure_shared_agent_token
sync_agent_container_defaults

if ! grep -Eq '^(OPENAI_API_KEY|DEEPSEEK_API_KEY)=.+' agent/.env; then
  echo "Warning: agent/.env does not contain an API key yet. The UI will start, but Agent replies will show a setup prompt." >&2
fi

docker compose up -d --build
docker compose ps

frontend_port="$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d= -f2-)"
backend_port="$(grep -E '^BACKEND_PORT=' .env | tail -n 1 | cut -d= -f2-)"

echo
echo "Deployment started."
echo "Frontend: http://localhost:${frontend_port:-5173}"
echo "Backend health: http://localhost:${backend_port:-8000}/health"
