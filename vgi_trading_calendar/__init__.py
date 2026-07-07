"""Stock-exchange trading-calendar math as a VGI worker.

The implementation is split so each concern stays focused:

- ``trading``          -- pure ``datetime`` math over the ``exchange_calendars``
  library; no Arrow or VGI dependency, directly unit-testable.
- ``trading_scalars``  -- per-row trading functions as VGI scalar functions
  (``is_trading_day``, ``next_trading_day``, ``market_open`` / ``market_close``,
  ...), positional-only with an optional ``exchange`` arity overload.
- ``trading_tables``   -- set-returning functions that want named ``exchange``
  arguments (``trading_sessions``, ``trading_schedule``) plus the ``exchanges``
  discovery table, exposed as table functions (VGI scalars cannot take named
  args).

``trading_calendar_worker.py`` at the repo root assembles these into the
``tcal`` catalog and runs the worker over stdio (or HTTP).
"""

from __future__ import annotations

__version__ = "0.1.0"
