"""Composed example queries that combine several ``tcal`` objects in one query.

Each example is defined once here and referenced from both the schema-level
``vgi.example_queries`` list (``worker.py``) and the example list of the table
function that drives the query (``tables.py``), so the agent simulator -- which
only shows per-object examples -- sees them too. Every expected result is
asserted in ``test/sql/trading.test``.

The scalars' ``exchange`` argument is a constant parameter and the table
functions only accept literal arguments, so the ``exchanges`` discovery table
cannot drive a per-exchange call; the compositions here pair the set-returning
functions with the per-row scalars instead.
"""

from __future__ import annotations

from vgi.metadata import FunctionExample

# trading_sessions + is_trading_day: rows -> 2026-04-06, 2026-05-04, 2026-08-31, 2026-12-28.
NYSE_OPEN_LONDON_CLOSED = FunctionExample(
    sql=(
        "SELECT s.session "
        "FROM tcal.main.trading_sessions(DATE '2026-01-01', DATE '2026-12-31') AS s "
        "WHERE NOT tcal.main.is_trading_day(s.session, 'XLON') "
        "ORDER BY s.session"
    ),
    description=(
        "NYSE sessions in 2026 on which the London Stock Exchange is closed (UK bank holidays "
        "such as Easter Monday and the Boxing Day substitute) -- days a US/UK pairs desk "
        "trades only one leg."
    ),
)

# trading_sessions + add_trading_days: the Wednesday 2026-11-25 trade settles Friday 11-27
# (Thanksgiving skipped); Friday 11-27 settles Monday 11-30.
T1_SETTLEMENT_THANKSGIVING_WEEK = FunctionExample(
    sql=(
        "SELECT s.session AS trade_date, tcal.main.add_trading_days(s.session, 1) AS settles_t1 "
        "FROM tcal.main.trading_sessions(DATE '2026-11-23', DATE '2026-11-30') AS s "
        "ORDER BY s.session"
    ),
    description=(
        "T+1 settlement date for a trade on each NYSE session of Thanksgiving week 2026 -- the "
        "Wednesday trade settles on Friday because the Thanksgiving holiday is skipped."
    ),
)

# trading_schedule + next_trading_day + market_open: 2026-11-27 -> 2026-11-30 14:30 UTC,
# 2026-12-24 -> 2026-12-28 14:30 UTC.
EARLY_CLOSE_NEXT_OPEN = FunctionExample(
    sql=(
        "SELECT sc.session, sc.market_close, "
        "tcal.main.next_trading_day(sc.session) AS next_session, "
        "tcal.main.market_open(tcal.main.next_trading_day(sc.session)) AS next_open "
        "FROM tcal.main.trading_schedule(DATE '2026-01-01', DATE '2026-12-31') AS sc "
        "WHERE sc.is_early_close "
        "ORDER BY sc.session"
    ),
    description=(
        "Every NYSE early-close half-day in 2026 with its early close time (UTC) and when the "
        "market next opens -- how long positions sit over the holiday break."
    ),
)

# trading_schedule (XNYS) joined to trading_schedule (XLON): 120 minutes on 27 sessions
# (from 2026-03-02) and 180 minutes on 15 sessions (from 2026-03-09, between the US DST
# change on 8 March and the UK change on 29 March).
TRANSATLANTIC_OVERLAP_DST = FunctionExample(
    sql=(
        "SELECT date_diff('minute', greatest(ny.market_open, ln.market_open), "
        "least(ny.market_close, ln.market_close)) AS overlap_minutes, "
        "count(*) AS n_sessions, min(ny.session) AS first_session "
        "FROM tcal.main.trading_schedule(DATE '2026-03-01', DATE '2026-04-30') AS ny "
        "JOIN tcal.main.trading_schedule(DATE '2026-03-01', DATE '2026-04-30', exchange := 'XLON') AS ln "
        "USING (session) "
        "GROUP BY overlap_minutes ORDER BY first_session"
    ),
    description=(
        "Minutes of overlap between NYSE and London trading hours on sessions both trade in "
        "March-April 2026: usually 2 hours, widening to 3 hours for the weeks when the US has "
        "moved to daylight saving time and the UK has not."
    ),
)

COMPOSED_EXAMPLES: list[FunctionExample] = [
    NYSE_OPEN_LONDON_CLOSED,
    T1_SETTLEMENT_THANKSGIVING_WEEK,
    EARLY_CLOSE_NEXT_OPEN,
    TRANSATLANTIC_OVERLAP_DST,
]
