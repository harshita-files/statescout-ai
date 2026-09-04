# Reporting API image (Track D).
# Build context is the repo root so the API can share `apps/agent/contracts.py`.
#   docker compose -f infra/docker-compose.yml --profile api up --build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer first so source edits do not invalidate the install.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --extra api

COPY apps ./apps
COPY services ./services
RUN uv sync --frozen --extra api

EXPOSE 8000

# Track D replaces this with the real ASGI app once services/api/main.py exists.
CMD ["uv", "run", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
