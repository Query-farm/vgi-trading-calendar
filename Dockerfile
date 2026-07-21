# Copyright 2026 Query Farm LLC - https://query.farm
#
# Single image serving BOTH transports of the vgi-trading-calendar worker:
#   docker run ... IMG            -> HTTP server on $PORT (default 8000; /health, VGI RPC)
#   docker run -i ... IMG stdio   -> stdio worker DuckDB spawns on-host
# See docker-entrypoint.sh. Keyless + stateless: all trading-calendar math is pure
# and offline (exchange-calendars), so there is no persistent state volume.
# The worker's Worker subclass lives in the repo-root script
# `trading_calendar_worker.py` (not the wheel), so both transports reference it by
# path; the `vgi_trading_calendar` package + vgi-python[http] come from the wheel.
# syntax=docker/dockerfile:1
FROM python:3.13-slim

ARG VERSION=0.0.0
ARG GIT_COMMIT=unknown
ARG SOURCE_URL=https://github.com/Query-farm/vgi-trading-calendar

LABEL org.opencontainers.image.title="vgi-trading-calendar" \
      org.opencontainers.image.description="Stock-exchange trading-calendar math (sessions, market hours, schedules) as a VGI worker for DuckDB/SQL (stdio + HTTP)" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.licenses="MIT" \
      farm.query.vgi.transports='["http","stdio"]'

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# curl backs the HEALTHCHECK and the CI /health smoke.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install the worker package + HTTP-serving extra from the source tree (version
# read from pyproject.toml by hatchling). Only the `vgi_trading_calendar` package
# ships in the wheel; the repo-root entry script is copied in separately below.
COPY pyproject.toml README.md LICENSE ./
COPY vgi_trading_calendar ./vgi_trading_calendar
RUN pip install '.[serve]'

# The repo-root Worker entry script (deliberately NOT in the wheel) — both
# transports reference it by path (/app/trading_calendar_worker.py).
COPY trading_calendar_worker.py ./

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=8s \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
