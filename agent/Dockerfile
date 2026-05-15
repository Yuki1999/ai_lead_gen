FROM node:22-bookworm-slim AS build

WORKDIR /app/agent

COPY agent/package*.json ./
RUN npm ci

COPY agent/ ./
RUN npm run build

FROM node:22-bookworm-slim

ENV NODE_ENV=production \
    PROJECT_ROOT=/app \
    AGENT_HOST=0.0.0.0 \
    AGENT_PORT=8011

WORKDIR /app/agent

COPY agent/package*.json ./
RUN npm ci --omit=dev

COPY --from=build /app/agent/dist ./dist
COPY skills /app/skills

EXPOSE 8011

CMD ["node", "dist/index.js"]
