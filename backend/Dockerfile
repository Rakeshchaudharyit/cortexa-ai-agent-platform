# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUFF_CACHE_DIR=/tmp/ruff_cache \
    MYPY_CACHE_DIR=/tmp/mypy_cache \
    PYTEST_ADDOPTS="-p no:cacheprovider"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 cortexa \
    && useradd --system --uid 10001 --gid cortexa --home /app --shell /usr/sbin/nologin cortexa \
    && mkdir -p /tmp/ruff_cache /tmp/mypy_cache /var/lib/cortexa/documents \
    && chown -R cortexa:cortexa /tmp/ruff_cache /tmp/mypy_cache /var/lib/cortexa/documents

# Dependency layer (cache-friendly)
COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN pip install --upgrade pip \
    && pip install -e ".[dev]" \
    && chmod +x /docker-entrypoint.sh \
    && chown -R cortexa:cortexa /app

# Entrypoint starts as root to fix volume ownership, then drops to cortexa.
USER root

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
