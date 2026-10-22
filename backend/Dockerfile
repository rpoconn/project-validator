# syntax=docker/dockerfile:1

# Targets:
#   runtime (default) - production API image
#   check             - lint, format check, type check and tests; the build fails if any fail

FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS deps
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM deps AS check
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked
COPY . .
RUN uv run ruff check . \
    && uv run ruff format --check . \
    && uv run mypy \
    && uv run pytest

FROM python:3.13-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /app/data \
    && chown app /app/data
COPY --from=deps /app/.venv /app/.venv
COPY src ./src
USER app
# Default DATABASE_URL resolves to /app/data/app.db; mount a volume here to keep data.
VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
