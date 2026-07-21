#!/bin/sh
# Copyright 2026 Query Farm LLC - https://query.farm
#
# Dispatch the single vgi-trading-calendar image into one of its transports:
#   http   (default) HTTP server on $PORT (vgi-serve --http: /health + VGI RPC)
#   stdio            a worker DuckDB spawns over stdio (on-host execution)
#   *                exec'd verbatim (debug escape hatch)
#
# The worker's TradingCalendarWorker subclass lives in the repo-root script
# /app/trading_calendar_worker.py (not the wheel), so both transports reference
# it by path. `vgi-serve` accepts a `./file.py` worker ref and finds the Worker.
set -e
case "${1:-http}" in
  http)  exec vgi-serve /app/trading_calendar_worker.py --http --host 0.0.0.0 --port "${PORT:-8000}" ;;
  stdio) shift 2>/dev/null || true; exec python /app/trading_calendar_worker.py "$@" ;;
  *)     exec "$@" ;;
esac
