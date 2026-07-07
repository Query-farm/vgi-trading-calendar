"""Set-returning trading / exchange-calendar table functions for DuckDB.

These expand to **many rows**, so they are exposed as **table functions** -- the
form that accepts DuckDB ``name := value`` arguments (``exchange``). The
per-row, single-value trading functions (``is_trading_day``, ``market_open``,
...) are *scalars* and live in :mod:`vgi_trading_calendar.trading_scalars`.

    SELECT * FROM tcal.trading_sessions(DATE '2026-01-01', DATE '2026-01-31');
    SELECT * FROM tcal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30', exchange := 'XNYS');
    SELECT * FROM tcal.exchanges;
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Annotated, ClassVar

import pyarrow as pa
from vgi.arguments import Arg
from vgi.metadata import FunctionExample
from vgi.table_function import (
    BindParams,
    ProcessParams,
    TableCardinality,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi_rpc.rpc import OutputCollector

from . import trading
from .meta import object_tags
from .schema_utils import field

_SRC = "trading_tables.py"

_TZ_TS = pa.timestamp("us", tz="UTC")
_EXCHANGE = Arg[str](
    "exchange",
    default=trading.DEFAULT_EXCHANGE,
    doc="Exchange MIC code (e.g. 'XNYS', 'XLON'). See tcal.exchanges.",
    choices=trading.list_exchanges(),
)


# ---------------------------------------------------------------------------
# trading_sessions(start, end, exchange := 'XNYS') -> (date)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _TradingSessionsArgs:
    """``trading_sessions(start, end, exchange := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Range start (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="Range end (inclusive).")]
    exchange: Annotated[str, _EXCHANGE]


_TRADING_SESSIONS_SCHEMA = pa.schema([field("date", pa.date32(), "A trading session in the range.", nullable=False)])


@init_single_worker
@bind_fixed_schema
class TradingSessionsFunction(TableFunctionGenerator[_TradingSessionsArgs]):
    """Every trading session in an inclusive ``[start, end]`` range, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _TRADING_SESSIONS_SCHEMA

    class Meta:
        """Function metadata."""

        name = "trading_sessions"
        description = "Every trading session in an inclusive [start, end] range"
        categories = ["calendar", "trading"]
        tags = {
            **object_tags(
                "Trading Sessions In Range",
                "Enumerate **every trading session in an inclusive `[start, end]` date range**, one "
                "per row -- the days the market is open, excluding weekends and exchange holidays. "
                "Takes `start` and `end` positionally plus an optional named `exchange` (default "
                "`'XNYS'`, NYSE). Both bounds are inclusive. Use it to expand a range into a "
                "session series you can join against, count, or window over. Dates outside the "
                "`exchange-calendars` coverage window simply do not appear. For other markets pass "
                "`exchange`; see `tcal.exchanges` for MIC codes.",
                "## trading_sessions(start, end, exchange := ...)\n\n"
                "Every **trading session in the inclusive `[start, end]` range**, one per row.\n\n"
                "Open days only (no weekends/holidays); `exchange` defaults to `'XNYS'`. Expand a "
                "range into a session series for joins/counts. See `tcal.exchanges`.",
                "trading sessions, list sessions, market days, open days, session series, "
                "trading calendar, nyse sessions, date range",
                _SRC,
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `date` | DATE | A trading session in the range. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM tcal.main.trading_sessions(DATE '2026-01-01', DATE '2026-01-31')",
                description="NYSE sessions in January 2026",
            ),
            FunctionExample(
                sql=(
                    "SELECT * FROM tcal.main.trading_sessions(DATE '2026-01-01', DATE '2026-01-31', exchange := 'XLON')"
                ),
                description="London sessions in January 2026",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_TradingSessionsArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_TradingSessionsArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        a = params.args
        days = trading.trading_sessions_in_range(a.start, a.end, a.exchange)
        out.emit(pa.RecordBatch.from_pydict({"date": days}, schema=params.output_schema))
        out.finish()


# ---------------------------------------------------------------------------
# trading_schedule(start, end, exchange := 'XNYS')
#   -> (session, market_open, market_close, is_early_close)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _TradingScheduleArgs:
    """``trading_schedule(start, end, exchange := ...)``."""

    start: Annotated[_dt.date, Arg(0, arrow_type=pa.date32(), doc="Range start (inclusive).")]
    end: Annotated[_dt.date, Arg(1, arrow_type=pa.date32(), doc="Range end (inclusive).")]
    exchange: Annotated[str, _EXCHANGE]


_TRADING_SCHEDULE_SCHEMA = pa.schema(
    [
        field("session", pa.date32(), "Trading session date.", nullable=False),
        field("market_open", _TZ_TS, "UTC market-open instant.", nullable=False),
        field("market_close", _TZ_TS, "UTC market-close instant.", nullable=False),
        field("is_early_close", pa.bool_(), "True if the session closes early.", nullable=False),
    ]
)


@init_single_worker
@bind_fixed_schema
class TradingScheduleFunction(TableFunctionGenerator[_TradingScheduleArgs]):
    """Per-session open / close / early-close schedule over ``[start, end]``."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _TRADING_SCHEDULE_SCHEMA

    class Meta:
        """Function metadata."""

        name = "trading_schedule"
        description = "Per-session open/close/early-close schedule for a date range"
        categories = ["calendar", "trading"]
        tags = {
            **object_tags(
                "Trading Schedule For Range",
                "Return the **per-session trading schedule over an inclusive `[start, end]` date "
                "range**: one row per session with its `session` date, UTC `market_open` and "
                "`market_close` instants, and an `is_early_close` flag. Takes `start` and `end` "
                "positionally plus an optional named `exchange` (default `'XNYS'`, NYSE). This is "
                "the set-returning companion to the scalar `market_open` / `market_close` / "
                "`is_early_close` functions -- use it to materialize a market-hours table for a "
                "period (note half-days like the day after Thanksgiving). Sessions outside the "
                "coverage window are omitted. See `tcal.exchanges` for MIC codes.",
                "## trading_schedule(start, end, exchange := ...)\n\n"
                "Per-session **open / close / early-close schedule** over `[start, end]`.\n\n"
                "One row per session: `session`, UTC `market_open`/`market_close`, "
                "`is_early_close`. `exchange` defaults to `'XNYS'`. Materializes a market-hours "
                "table (half-days flagged). See `tcal.exchanges`.",
                "trading schedule, market hours, open close times, session schedule, early close, "
                "half day, trading hours table, nyse schedule",
                _SRC,
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `session` | DATE | Trading session date. |\n"
                "| `market_open` | TIMESTAMPTZ | UTC market-open instant. |\n"
                "| `market_close` | TIMESTAMPTZ | UTC market-close instant. |\n"
                "| `is_early_close` | BOOLEAN | True if the session closes early. |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM tcal.main.trading_schedule(DATE '2026-11-25', DATE '2026-11-30')",
                description="NYSE schedule around Thanksgiving (note the early close)",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_TradingScheduleArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=None, max=None)

    @classmethod
    def process(cls, params: ProcessParams[_TradingScheduleArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        a = params.args
        rows = trading.trading_schedule(a.start, a.end, a.exchange)
        out.emit(
            pa.RecordBatch.from_pydict(
                {
                    "session": [r[0] for r in rows],
                    "market_open": [r[1] for r in rows],
                    "market_close": [r[2] for r in rows],
                    "is_early_close": [r[3] for r in rows],
                },
                schema=params.output_schema,
            )
        )
        out.finish()


# ---------------------------------------------------------------------------
# exchanges -> (code)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class _NoArgs:
    """The scan-backed ``exchanges`` table takes no arguments."""


_EXCHANGES_SCHEMA = pa.schema([field("code", pa.string(), "Exchange MIC code (e.g. 'XNYS').", nullable=False)])


@init_single_worker
@bind_fixed_schema
class ExchangesFunction(TableFunctionGenerator[_NoArgs]):
    """Every supported exchange MIC code, one per row."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = _EXCHANGES_SCHEMA

    class Meta:
        """Function metadata."""

        name = "exchanges"
        description = "List every supported exchange calendar MIC code"
        categories = ["calendar", "trading"]
        tags = {
            **object_tags(
                "Supported Exchanges Catalog",
                "List **every supported stock-exchange trading calendar**, one MIC code per row. "
                "These are the codes you pass as the `exchange` argument to the trading functions "
                "(`is_trading_day`, `market_open`, `trading_schedule`, ...). `'XNYS'` (NYSE) is "
                "merely the default; coverage spans roughly a hundred exchange calendars via the "
                "`exchange-calendars` library (e.g. `'XLON'` London, `'XTKS'` Tokyo, `'XNAS'` "
                "Nasdaq). This is a discovery table -- query or filter it to find the MIC code for "
                "a market.",
                "## exchanges\n\n"
                "Every supported **exchange MIC code**, one per row.\n\n"
                "These are the valid `exchange` arguments for the trading functions; `'XNYS'` is "
                "just the default. ~100 calendars (`'XLON'`, `'XTKS'`, `'XNAS'`, ...).",
                "exchanges, list exchanges, mic codes, supported exchanges, trading calendars, "
                "discovery, xnys xlon xtks, stock exchange codes",
                _SRC,
            ),
            "vgi.executable_examples": (
                '[{"description": "List all supported exchange MIC codes.", '
                '"sql": "SELECT code FROM tcal.main.exchanges ORDER BY code"}, '
                '{"description": "Confirm the NYSE (XNYS) calendar is available.", '
                '"sql": "SELECT count(*) AS n FROM tcal.main.exchanges WHERE code = \'XNYS\'"}]'
            ),
            "vgi.result_columns_md": (
                "| column | type | description |\n"
                "| --- | --- | --- |\n"
                "| `code` | VARCHAR | Exchange MIC code (e.g. 'XNYS'). |\n"
            ),
        }
        examples = [
            FunctionExample(
                sql="SELECT * FROM tcal.main.exchanges ORDER BY code",
                description="All supported exchange codes",
            ),
        ]

    @classmethod
    def cardinality(cls, params: BindParams[_NoArgs]) -> TableCardinality:
        """Estimate the output row count for the query planner."""
        return TableCardinality(estimate=120, max=1000)

    @classmethod
    def process(cls, params: ProcessParams[_NoArgs], state: None, out: OutputCollector) -> None:
        """Emit the function's output rows into the collector."""
        out.emit(pa.RecordBatch.from_pydict({"code": trading.list_exchanges()}, schema=params.output_schema))
        out.finish()


# NB: ExchangesFunction is intentionally NOT registered as a standalone table
# function — it backs the scan `Table(name="exchanges", …)` in calendar_worker.py,
# so the exchange MIC codes are exposed once, as a plain table (no parens).
TRADING_TABLE_FUNCTIONS: list[type] = [
    TradingSessionsFunction,
    TradingScheduleFunction,
]
