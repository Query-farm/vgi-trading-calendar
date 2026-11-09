# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.50.0",
#     "exchange-calendars>=4.5",
# ]
# ///
"""Repo-root shim for the trading-calendar worker.

The worker lives in :mod:`vgi_trading_calendar.worker` (installed as the
``vgi-trading-calendar-worker`` console script, so
``uvx --from git+https://github.com/Query-farm/vgi-trading-calendar vgi-trading-calendar-worker``
works). This file keeps ``uv run trading_calendar_worker.py`` working from a
checkout.
"""

from __future__ import annotations

from vgi_trading_calendar.worker import TradingCalendarWorker, main

__all__ = ["TradingCalendarWorker", "main"]

if __name__ == "__main__":
    main()
