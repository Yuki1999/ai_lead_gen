FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev

COPY backend/ ./

WORKDIR /app
COPY SkyWalker-Surgical-Robot-Sales-Brochure-International.pdf ./
COPY ["02-鸿鹄产品介绍Skywalker TKA Brochure.pdf", "./"]
COPY 0_6.mp4 ./

WORKDIR /app/backend
EXPOSE 8000

CMD ["uv", "run", "--locked", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
