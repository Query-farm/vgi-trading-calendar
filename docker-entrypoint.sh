#!/bin/sh
# Copyright 2026 Query Farm LLC - https://query.farm
#
# Dispatch the single vgi-trading-calendar image into one of its transports:
#   http   (default) HTTP server on $PORT (vgi-serve --http: /health + VGI RPC)
#   stdio            a worker DuckDB spawns over stdio (on-host execution)
#   *                exec'd verbatim (debug escape hatch)
#
# The worker's TradingCalendarWorker subclass ships in the wheel
# (vgi_trading_calendar.worker); stdio runs the installed console script.
set -e
case "${1:-http}" in
  http)  exec vgi-serve vgi_trading_calendar.worker:TradingCalendarWorker --http --host 0.0.0.0 --port "${PORT:-8000}" ;;
  stdio) shift 2>/dev/null || true; exec vgi-trading-calendar-worker "$@" ;;
  *)     exec "$@" ;;
esac
