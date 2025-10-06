# syntax=docker/dockerfile:1.6

FROM python:3.12.6-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip build \
    && python -m build --wheel --outdir /dist


FROM python:3.12.6-slim AS runtime

ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=0.0.0

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    APP_USER=adhash \
    APP_HOME=/workspace

LABEL org.opencontainers.image.title="Adaptive HashMap CLI" \
      org.opencontainers.image.description="Containerised Adaptive Hash Map CLI with metrics dashboard" \
      org.opencontainers.image.source="https://github.com/${GITHUB_REPOSITORY:-unknown}" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_DATE"

WORKDIR /tmp

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash "$APP_USER"

COPY --from=builder /dist /tmp/dist
RUN python -m pip install --no-deps /tmp/dist/*.whl \
    && rm -rf /tmp/dist

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR $APP_HOME
RUN chown -R "$APP_USER":"$APP_USER" $APP_HOME

ENV ADHASH_METRICS_HOST=0.0.0.0 \
    ADHASH_METRICS_PORT=9090 \
    ADHASH_TOKEN=""

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${ADHASH_METRICS_PORT:-9090}/healthz" || exit 1

USER $APP_USER

ENTRYPOINT ["/entrypoint.sh"]
CMD ["serve"]
