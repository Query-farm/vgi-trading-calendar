# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "vgi-python[http]>=0.16.0",
#     "exchange-calendars>=4.5",
# ]
# ///
"""VGI worker exposing stock-exchange trading-calendar math to SQL.

Assembles the trading-calendar functions in ``vgi_trading_calendar`` into a
single ``tcal`` catalog and runs the worker over stdio (DuckDB subprocess) or
HTTP.

Usage:
    uv run trading_calendar_worker.py   # serve over stdio (DuckDB subprocess)

    INSTALL vgi FROM community; LOAD vgi;
    ATTACH 'tcal' (TYPE vgi, LOCATION 'uv run trading_calendar_worker.py');

    -- Trading / exchange calendars (default exchange 'XNYS' = NYSE):
    SELECT tcal.main.is_trading_day(DATE '2026-01-01');            -- false (market holiday)
    SELECT tcal.main.next_trading_day(DATE '2026-01-01');          -- 2026-01-02
    SELECT tcal.main.market_close(DATE '2026-11-27', 'XNYS');      -- early close after Thanksgiving
    SELECT * FROM tcal.main.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');
    SELECT * FROM tcal.main.exchanges;
"""

from __future__ import annotations

import json

from vgi import Worker
from vgi.catalog import Catalog, Schema, Table

from vgi_trading_calendar.meta import examples_to_tag, keywords_array
from vgi_trading_calendar.scalars import SCALAR_FUNCTIONS
from vgi_trading_calendar.tables import TABLE_FUNCTIONS, ExchangesFunction

_FUNCTIONS: list[type] = [
    *SCALAR_FUNCTIONS,
    *TABLE_FUNCTIONS,
]

# VGI413 — the schema's `vgi.categories` registry (see below) requires every
# categorizable object to carry a `vgi.category` naming one of the registry
# entries. Rather than thread a category argument through every function's
# `Meta`, map each function by name and stamp `vgi.category` onto its tags here;
# `vgi.resolve_metadata` reads `Meta.tags` live at discovery time, so mutating it
# before the worker serves is sufficient.
_CATEGORY_BY_NAME: dict[str, str] = {
    # Trading-session tests, navigation, arithmetic, and enumeration
    "is_trading_day": "sessions",
    "next_trading_day": "sessions",
    "previous_trading_day": "sessions",
    "add_trading_days": "sessions",
    "trading_days_between": "sessions",
    "trading_sessions": "sessions",
    # Market open/close instants, early closes, and the per-session schedule
    "market_open": "market-hours",
    "market_close": "market-hours",
    "is_early_close": "market-hours",
    "trading_schedule": "market-hours",
    # NB: `exchanges` is a scan-backed TABLE (see below), not a function, so it
    # carries `vgi.category` on the Table directly and is intentionally absent
    # from this function-name map.
}

# VGI515 — the native `duckdb_functions().examples` column carries SQL text only,
# so each `Meta.examples` FunctionExample's `description` is dropped on the wire and
# vgi-lint sees an undescribed example. Re-emit every function's examples through the
# `vgi.example_queries` tag (which preserves the description) and clear the native
# list so there is no undescribed duplicate. The same loop stamps `vgi.category`.
for _fn in _FUNCTIONS:
    _meta = _fn.Meta  # type: ignore[attr-defined]  # every registered function class defines Meta
    _tags = {**dict(_meta.tags), "vgi.category": _CATEGORY_BY_NAME[_meta.name]}
    _examples = list(getattr(_meta, "examples", ()))
    if _examples:
        _tags["vgi.example_queries"] = examples_to_tag(_examples)
        _meta.examples = []
    _meta.tags = _tags

_CATALOG_DESCRIPTION_LLM = (
    "Stock-exchange trading-calendar math for SQL (default exchange 'XNYS' = NYSE): test whether a "
    "date is a trading session, find the next / previous session, advance a date by N sessions and "
    "count sessions between two dates, get market open/close instants as timezone-aware UTC "
    "timestamps (including early closes such as the day after US Thanksgiving), list the trading "
    "sessions and the per-session schedule for a date range, and enumerate the ~100 supported "
    "exchange MIC codes (e.g. 'XNAS' Nasdaq, 'XLON' London, 'XTKS' Tokyo). Use for trading-day, "
    "settlement, and market-hours questions in SQL. For public holidays, business days, and "
    "RFC-5545 recurrence, see the companion vgi-calendar worker."
)

_CATALOG_DESCRIPTION_MD = (
    "# Trading-Day & Market-Hours Math in SQL\n\n"
    "**`tcal` brings stock-exchange trading calendars directly into DuckDB SQL — no ETL, no "
    "Python glue, just `SELECT`.** Ask whether a date is a trading session, advance or count "
    "trading days, find the next or previous session, or check market open/close hours (including "
    "early closes) for the NYSE and ~100 other exchanges, all as ordinary SQL expressions and "
    "table functions.\n\n"
    "This VGI worker is for analysts, data engineers, and application developers who need correct "
    "market-calendar logic close to their data: trading-day filtering, settlement (T+N) date "
    "math, session alignment of fills and ticks, and market-hours analytics. It exposes a single "
    "`tcal` catalog (schema `main`) over Apache Arrow, so every function streams results back to "
    "DuckDB with native types — `DATE`, `TIMESTAMP`, and `TIMESTAMPTZ` round-trip cleanly. "
    "Coverage is global, not US-centric: roughly a hundred exchange calendars are supported, and "
    "`'XNYS'` (NYSE) is merely the default argument, not a limit.\n\n"
    "Trading calendars are provided by "
    "[exchange-calendars](https://github.com/gerrymanoim/exchange_calendars) "
    "([docs](https://exchange-calendars.readthedocs.io/)), the maintained successor to "
    "Quantopian's `trading_calendars`, covering roughly a hundred exchanges including early "
    "closes and holiday sessions. A **session** is a trading day; `market_open` / `market_close` "
    "are timezone-aware **UTC** instants. Coverage is the library's default window (roughly two "
    "decades back to about a year ahead — future exchange holidays are only defined so far); a "
    "date outside that window resolves to `NULL` / no rows rather than raising.\n\n"
    "Per-row questions are answered by scalar functions you can drop straight into a projection "
    "or predicate; set-returning questions — a range of trading sessions, an expanded "
    "per-session schedule — are table functions. The exchange is an ordinary argument that "
    "defaults to `'XNYS'`."
)

_SCHEMA_DESCRIPTION_LLM = (
    "Stock-exchange trading-calendar functions: trading-session tests and navigation, "
    "session arithmetic and counts, market open/close instants (including early closes), "
    "trading-session and per-session-schedule listings, and a discovery table of supported "
    "exchange MIC codes."
)

_SCHEMA_DESCRIPTION_MD = (
    "## Trading-day & market-hours math\n\n"
    "Stock-exchange trading-calendar functions over Apache Arrow, exposed as ordinary DuckDB "
    "SQL.\n\n"
    "**Key concepts**\n\n"
    "- Scalar functions answer one question per row and slot into a projection or predicate.\n"
    "- Table functions return sets of rows: a range of trading sessions or an expanded "
    "per-session schedule.\n"
    "- The exchange is an ordinary argument; `'XNYS'` (NYSE) is only a default, not a limit — "
    "coverage spans ~100 exchange calendars.\n"
    "- A *session* is a trading day; `market_open` / `market_close` are timezone-aware **UTC** "
    "instants. `DATE`, `TIMESTAMP`, and `TIMESTAMPTZ` round-trip natively over Arrow.\n\n"
    "**When to use it**\n\n"
    "Reach for this schema for trading-day filtering, settlement (T+N) date math, session "
    "alignment of fills and ticks, and market-hours analytics."
)

# VGI506/VGI515 — representative, catalog-qualified, described example queries for
# the schema. Every reference is fully qualified (`tcal.main.<fn>`) so each entry
# executes as written against the attached worker, and each carries a human-readable
# description (a plain SQL string is not a described-example list).
_SCHEMA_EXAMPLE_QUERIES = json.dumps(
    [
        {
            "description": "Is New Year's Day 2026 an NYSE trading session? (No — it is a holiday.)",
            "sql": "SELECT tcal.main.is_trading_day(DATE '2026-01-01') AS is_session",
        },
        {
            "description": "Is 3 July 2026 (US Independence Day observed) a London Stock Exchange session?",
            "sql": "SELECT tcal.main.is_trading_day(DATE '2026-07-03', 'XLON') AS is_session",
        },
        {
            "description": "The first NYSE session strictly after New Year's Day 2026.",
            "sql": "SELECT tcal.main.next_trading_day(DATE '2026-01-01') AS next_session",
        },
        {
            "description": "The last NYSE session strictly before 2 January 2026.",
            "sql": "SELECT tcal.main.previous_trading_day(DATE '2026-01-02') AS prev_session",
        },
        {
            "description": "Advance a trade date by 10 NYSE sessions (settlement-style date math).",
            "sql": "SELECT tcal.main.add_trading_days(DATE '2026-01-02', 10) AS settle_date",
        },
        {
            "description": "Count NYSE sessions in January 2026 via the half-open [start, end) interval.",
            "sql": "SELECT tcal.main.trading_days_between(DATE '2026-01-01', DATE '2026-02-01') AS n_sessions",
        },
        {
            "description": "NYSE market-open instant (UTC) for 2 January 2026.",
            "sql": "SELECT tcal.main.market_open(DATE '2026-01-02') AS open_utc",
        },
        {
            "description": "NYSE early close (UTC) the day after US Thanksgiving 2026.",
            "sql": "SELECT tcal.main.market_close(DATE '2026-11-27') AS close_utc",
        },
        {
            "description": "Flag the day after US Thanksgiving 2026 as an early-close half-day.",
            "sql": "SELECT tcal.main.is_early_close(DATE '2026-11-27') AS early_close",
        },
        {
            "description": "Count the NYSE trading sessions in January 2026.",
            "sql": (
                "SELECT count(*) AS n_sessions FROM tcal.main.trading_sessions(DATE '2026-01-01', DATE '2026-01-31')"
            ),
        },
        {
            "description": "Half-days in the NYSE Thanksgiving-week schedule, with their early close time.",
            "sql": (
                "SELECT session, market_close "
                "FROM tcal.main.trading_schedule(DATE '2026-11-25', DATE '2026-11-30') "
                "WHERE is_early_close"
            ),
        },
        {
            "description": "The first five supported exchange MIC codes, alphabetically.",
            "sql": "SELECT code FROM tcal.main.exchanges ORDER BY code LIMIT 5",
        },
    ]
)

# VGI311 — the `exchanges` reference dataset always returns the same rows, so we
# expose it as a regular scan-backed TABLE: the `Table(function=…)` form serves
# the rows of the backing generator directly, letting consumers write
# `SELECT * FROM tcal.main.exchanges` (no parentheses) with no redundant
# view-over-a-table-function layer (see vgi-lint VGI145).
_EXCHANGES_TABLE = Table(
    name="exchanges",
    function=ExchangesFunction,
    comment="Discovery table of every supported stock-exchange trading-calendar MIC code.",
    # Each MIC code uniquely identifies one exchange calendar -> natural primary key.
    # `code` is always populated (VGI804 wants NOT NULL declared alongside the key).
    primary_key=(("code",),),
    not_null=("code",),
    column_comments={
        "code": "Exchange MIC code (e.g. 'XNYS' = NYSE, 'XLON' = London).",
    },
    tags={
        "vgi.title": "Supported Exchanges (table)",
        "vgi.category": "discovery",
        "vgi.doc_llm": (
            "A ready-to-scan **discovery table** of every supported stock-exchange trading "
            "calendar, one MIC code per row. These are the codes you pass as the `exchange` "
            "argument to the trading functions (`is_trading_day`, `market_open`, "
            "`trading_schedule`, ...). Reference it directly by name (no parentheses) in a "
            "`FROM` clause. "
            "`'XNYS'` (NYSE) is merely the default; coverage spans roughly a hundred "
            "exchange calendars via `exchange-calendars` (e.g. `'XLON'` London, `'XTKS'` Tokyo, "
            "`'XNAS'` Nasdaq)."
        ),
        "vgi.doc_md": (
            "## exchanges (table)\n\n"
            "Every supported **exchange MIC code**, one per row, as a plain table.\n\n"
            "The valid `exchange` arguments for the trading functions; `'XNYS'` is just the "
            "default. Scan it directly by name (no parentheses). "
            "~100 calendars (`'XLON'`, `'XTKS'`, `'XNAS'`, ...)."
        ),
        "vgi.keywords": keywords_array(
            "exchanges, list exchanges, mic codes, supported exchanges, trading calendars, "
            "discovery, xnys xlon xtks, stock exchange codes, exchanges table"
        ),
        "domain": "date-and-time",
        "category": "trading-calendar",
        "topic": "supported-exchanges",
        "vgi.example_queries": (
            '[{"description": "List all supported exchange MIC codes.", '
            '"sql": "SELECT code FROM tcal.main.exchanges ORDER BY code"}, '
            '{"description": "Confirm the NYSE (XNYS) calendar is available.", '
            '"sql": "SELECT count(*) AS n FROM tcal.main.exchanges WHERE code = \'XNYS\'"}]'
        ),
    },
)


# VGI413 — the schema's category registry. Ordered; each object's `vgi.category`
# (stamped above / on the table) names one of these. Drives listing navigation
# and SEO sections.
_SCHEMA_CATEGORIES = json.dumps(
    [
        {
            "name": "sessions",
            "description": "Trading-session tests, navigation, arithmetic, and enumeration.",
        },
        {
            "name": "market-hours",
            "description": "Market open/close instants, early closes, and per-session schedules.",
        },
        {"name": "discovery", "description": "Reference table of supported exchange MIC codes."},
    ]
)

# VGI509 — at least one guaranteed-runnable example at the catalog level. Each is
# fully catalog-qualified and offline/deterministic so it runs as written.
_EXECUTABLE_EXAMPLES = json.dumps(
    [
        {
            "name": "is-market-open",
            "description": "Whether a date is an NYSE trading session (New Year's Day is a holiday).",
            "sql": "SELECT tcal.main.is_trading_day(DATE '2026-01-01') AS is_session",
        },
        {
            "name": "next-nyse-session",
            "description": "The first NYSE session strictly after a given date.",
            "sql": "SELECT tcal.main.next_trading_day(DATE '2026-01-01') AS next_session",
        },
        {
            "name": "list-exchanges",
            "description": "A few of the supported exchange MIC codes.",
            "sql": "SELECT code FROM tcal.main.exchanges ORDER BY code LIMIT 5",
        },
    ]
)

# VGI152 — the fixed agent-suitability task suite used by `vgi-lint simulate`.
# Each task's `prompt` is all the analyst sees; `reference_sql` is grader-only
# and must be deterministic. Chosen to exercise the trading-session, navigation,
# market-hours, and discovery surface. Every expected value is also asserted in
# test/sql/trading.test.
_AGENT_TEST_TASKS = json.dumps(
    [
        {
            "name": "next-nyse-session-after-new-year",
            "prompt": (
                "Using the tcal worker, what is the first New York Stock Exchange trading session "
                "strictly after 1 January 2026? Return a single date."
            ),
            "reference_sql": "SELECT tcal.main.next_trading_day(DATE '2026-01-01') AS next_session",
            "ignore_column_names": True,
        },
        {
            "name": "add-ten-nyse-sessions",
            "prompt": (
                "Using the tcal worker, what calendar date is 10 New York Stock Exchange trading "
                "sessions after 2 January 2026 (skipping weekends and exchange holidays)? Return a "
                "single date."
            ),
            "reference_sql": "SELECT tcal.main.add_trading_days(DATE '2026-01-02', 10) AS result",
            "ignore_column_names": True,
        },
        {
            "name": "count-nyse-sessions-january-2026",
            "prompt": (
                "Using the tcal worker, how many New York Stock Exchange trading sessions are there "
                "in January 2026 — that is, in the half-open range from 1 January 2026 up to (but "
                "not including) 1 February 2026? Return a single integer."
            ),
            "reference_sql": ("SELECT tcal.main.trading_days_between(DATE '2026-01-01', DATE '2026-02-01') AS n"),
            "ignore_column_names": True,
        },
        {
            "name": "nyse-early-close-instant",
            "prompt": (
                "Using the tcal worker, at what UTC timestamp does the New York Stock Exchange close "
                "on 27 November 2026 (the day after US Thanksgiving, an early-close half-day)? "
                "Return a single timestamp."
            ),
            "reference_sql": "SELECT tcal.main.market_close(DATE '2026-11-27') AS market_close",
            "ignore_column_names": True,
        },
        {
            "name": "london-trades-on-us-july-4-observed",
            "prompt": (
                "Using the tcal worker, is 3 July 2026 a trading session on the London Stock "
                "Exchange (MIC code 'XLON')? It is a US market holiday (observed Independence Day) "
                "but London is unaffected. Return a single boolean."
            ),
            "reference_sql": "SELECT tcal.main.is_trading_day(DATE '2026-07-03', 'XLON') AS is_session",
            "ignore_column_names": True,
        },
        {
            "name": "previous-nyse-session-before-jan-2",
            "prompt": (
                "Using the tcal worker, what is the last New York Stock Exchange trading session "
                "strictly before 2 January 2026? Return a single date."
            ),
            "reference_sql": "SELECT tcal.main.previous_trading_day(DATE '2026-01-02') AS prev_session",
            "ignore_column_names": True,
        },
        {
            "name": "nyse-open-instant-jan-2",
            "prompt": (
                "Using the tcal worker, at what UTC timestamp does the New York Stock Exchange open "
                "on 2 January 2026? Return a single timestamp."
            ),
            "reference_sql": "SELECT tcal.main.market_open(DATE '2026-01-02') AS market_open",
            "ignore_column_names": True,
        },
        {
            "name": "is-nyse-early-close-after-thanksgiving",
            "prompt": (
                "Using the tcal worker, is 27 November 2026 (the day after US Thanksgiving) an "
                "early-close half-day session on the New York Stock Exchange? Return a single "
                "boolean."
            ),
            "reference_sql": "SELECT tcal.main.is_early_close(DATE '2026-11-27') AS early_close",
            "ignore_column_names": True,
        },
        {
            "name": "count-nyse-sessions-via-trading-sessions",
            "prompt": (
                "Using the tcal worker, list the New York Stock Exchange trading sessions from 1 "
                "January 2026 through 31 January 2026 (inclusive) and return how many there are as "
                "a single integer."
            ),
            "reference_sql": (
                "SELECT count(*) AS n_sessions FROM tcal.main.trading_sessions(DATE '2026-01-01', DATE '2026-01-31')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "thanksgiving-schedule-early-close-flag",
            "prompt": (
                "Using the tcal worker, in the New York Stock Exchange schedule for 27 November "
                "2026, is that session flagged as an early close? Return a single boolean."
            ),
            "reference_sql": (
                "SELECT is_early_close FROM tcal.main.trading_schedule(DATE '2026-11-27', DATE '2026-11-27')"
            ),
            "ignore_column_names": True,
        },
        {
            "name": "nyse-in-supported-exchanges",
            "prompt": (
                "Using the tcal worker, confirm the New York Stock Exchange (MIC code 'XNYS') is "
                "one of the supported exchange calendars by returning how many rows of the "
                "supported-exchanges list have that code (expect 1). Return a single integer."
            ),
            "reference_sql": "SELECT count(*) AS n FROM tcal.main.exchanges WHERE code = 'XNYS'",
            "ignore_column_names": True,
        },
    ]
)


_TRADING_CALENDAR_CATALOG = Catalog(
    name="tcal",
    default_schema="main",
    comment="Stock-exchange trading-calendar math for SQL: sessions, market hours, and schedules",
    tags={
        "vgi.title": "Trading-Day & Market-Hours Math",
        "vgi.keywords": keywords_array(
            "trading day, trading calendar, exchange calendar, trading session, market open, "
            "market close, market hours, early close, half day, settlement, t+n, "
            "nyse, nasdaq, lse, tokyo, xnys, xnas, xlon, xtks, mic code, exchange, "
            "next trading day, session, date math"
        ),
        "vgi.doc_llm": _CATALOG_DESCRIPTION_LLM,
        "vgi.doc_md": _CATALOG_DESCRIPTION_MD,
        "vgi.author": "Query.Farm",
        "vgi.copyright": "Copyright 2026 Query Farm LLC - https://query.farm",
        "vgi.license": "MIT",
        "vgi.support_contact": "https://github.com/Query-farm/vgi-trading-calendar/issues",
        "vgi.support_policy_url": "https://github.com/Query-farm/vgi-trading-calendar/blob/main/README.md",
        "vgi.executable_examples": _EXECUTABLE_EXAMPLES,
        "vgi.agent_test_tasks": _AGENT_TEST_TASKS,
    },
    source_url="https://github.com/Query-farm/vgi-trading-calendar",
    schemas=[
        Schema(
            name="main",
            comment="Stock-exchange trading-calendar math for SQL",
            tags={
                "vgi.title": "Trading calendars — main",
                "vgi.keywords": keywords_array(
                    "trading day, trading session, next trading day, add trading days, "
                    "market open, market close, early close, trading schedule, exchange calendar, "
                    "exchanges, mic code"
                ),
                # VGI123 classifying tags use BARE keys (not vgi.-namespaced).
                "domain": "date-and-time",
                "category": "trading-calendar",
                "topic": "trading-sessions-market-hours",
                "vgi.categories": _SCHEMA_CATEGORIES,
                "vgi.example_queries": _SCHEMA_EXAMPLE_QUERIES,
                "vgi.doc_llm": _SCHEMA_DESCRIPTION_LLM,
                "vgi.doc_md": _SCHEMA_DESCRIPTION_MD,
            },
            functions=list(_FUNCTIONS),
            tables=[_EXCHANGES_TABLE],
        ),
    ],
)


class TradingCalendarWorker(Worker):
    """Worker process hosting the ``tcal`` trading-calendar catalog."""

    catalog = _TRADING_CALENDAR_CATALOG


def main() -> None:
    """Run the trading-calendar worker process (stdio or, via flags, HTTP)."""
    TradingCalendarWorker.main()


if __name__ == "__main__":
    main()
