# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.production DJANGO_DEBUG=false PORT=10000
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY config ./config
COPY manage.py ./
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint
# Apenas valores fictícios no build. collectstatic não conecta ao banco/APIs.
RUN DATABASE_URL='postgresql://build:build@localhost/build?sslmode=disable' \
    DJANGO_SECRET_KEY='build-only-not-a-runtime-secret' \
    python manage.py collectstatic --no-input
USER app
EXPOSE 10000
ENTRYPOINT ["/usr/local/bin/entrypoint"]
