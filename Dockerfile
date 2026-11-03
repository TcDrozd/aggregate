# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13

FROM ghcr.io/astral-sh/uv:0.13.7 AS uv

# Build: resolve the locked runtime dependencies into /app/.venv.
FROM python:${PYTHON_VERSION}-slim AS build
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Runtime: no uv, no build tools, non-root.
FROM python:${PYTHON_VERSION}-slim
RUN useradd --uid 1000 --user-group --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin aggregate \
    && mkdir /data \
    && chown aggregate:aggregate /data
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    AGGREGATE_DATABASE_URL=sqlite:////data/aggregate.db
WORKDIR /app
USER aggregate
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
ENTRYPOINT ["/app/docker-entrypoint.sh"]
