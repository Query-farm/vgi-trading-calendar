"""Per-row scalar trading / exchange-calendar functions.

Every function here is a true DuckDB **scalar** -- one value per row in, one out
-- so it works inline in a projection or predicate:

    SELECT is_trading_day(trade_date)            FROM fills;
    SELECT trade_date, market_close(trade_date, 'XLON') FROM fills;

Like every VGI scalar, these take **positional** arguments and resolve overloads
by *arity* -- ``name := value`` is a table-function feature, not a scalar one. So
the optional ``exchange`` argument is exposed as
a second arity overload that shares the function name; it defaults to ``'XNYS'``
(New York Stock Exchange):

    is_trading_day(date)            -- exchange defaults to 'XNYS'
    is_trading_day(date, exchange)  -- explicit exchange MIC code

Set-returning trading functions (``trading_sessions``, ``trading_schedule``,
``exchanges``) take named arguments and live in
:mod:`vgi_trading_calendar.tables`.
"""

from __future__ import annotations

from typing import Annotated

import pyarrow as pa
from vgi.arguments import ConstParam, Param, Returns
from vgi.metadata import FunctionExample
from vgi.scalar_function import ScalarFunction

from . import core
from .meta import object_tags

_SRC = "scalars.py"

_DEFAULT = core.DEFAULT_EXCHANGE
_TZ_TS = pa.timestamp("us", tz="UTC")
_EXCHANGE_DOC = "Exchange MIC code, e.g. 'XNYS', 'XNAS', 'XLON'. See tcal.exchanges."
# Machine-readable constraint (VGI317): enumerate the accepted exchange codes so
# agents discover valid inputs via vgi_function_arguments() instead of guessing.
_EXCHANGE_CHOICES = core.list_exchanges()


# ---------------------------------------------------------------------------
# is_trading_day(date[, exchange]) -> BOOLEAN
# ---------------------------------------------------------------------------


def _is_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.BooleanArray:
    out = [None if d is None else core.is_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsTradingDayFunction(ScalarFunction):
    """``is_trading_day(date)`` -- True if the date is an NYSE trading session."""

    class Meta:
        """Function metadata."""

        name = "is_trading_day"
        description = "True if a date is a trading session (exchange defaults to 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Is Trading Day",
            "Test whether a date is a **trading session** on a stock exchange -- i.e. the market is "
            "open, not a weekend or exchange holiday. This one-argument overload uses the default "
            "exchange `'XNYS'` (NYSE). Trading calendars differ from public-holiday calendars "
            "(exchanges have their own closures), so this is distinct from `is_business_day`. "
            "Returns `BOOLEAN` per row (`NULL` date -> `NULL`); dates outside the "
            "`exchange-calendars` coverage window return `NULL`. For other markets use "
            "`is_trading_day(date, exchange)`; see `tcal.exchanges` for MIC codes.",
            "## is_trading_day(date)\n\n"
            "True if `date` is an **NYSE trading session** (exchange `'XNYS'`).\n\n"
            "Distinct from `is_business_day` -- exchanges have their own holiday calendar. Per-row "
            "`BOOLEAN`; `NULL` outside the calendar window. See the exchange overload and "
            "`tcal.exchanges`.",
            "is trading day, trading session, market open day, exchange open, nyse session, "
            "stock market open, trading calendar",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.is_trading_day(DATE '2026-01-01')",
                description="New Year's Day is not an NYSE session",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to evaluate.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_trading_day_column(date, exchange=_DEFAULT)


class IsTradingDayExchangeFunction(ScalarFunction):
    """``is_trading_day(date, exchange)`` -- True if a session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "is_trading_day"
        description = "True if a date is a trading session on an exchange"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Is Trading Day On Exchange",
            "Test whether a date is a **trading session** on a given exchange. The `exchange` "
            "argument is optional and defaults to `'XNYS'` (NYSE); pass a MIC code (e.g. `'XLON'` "
            "for the London Stock Exchange, `'XTKS'` for Tokyo) for another market. Each exchange "
            "has its own holiday/weekend calendar via the "
            "`exchange-calendars` library. Returns `BOOLEAN` per row (`NULL` date -> `NULL`); "
            "dates outside the calendar's coverage window return `NULL`. List valid MIC codes with "
            "`tcal.exchanges`.",
            "## is_trading_day(date[, exchange])\n\n"
            "True if `date` is a **trading session**; `exchange` defaults to `'XNYS'` (MIC code, "
            "e.g. `'XLON'`).\n\n"
            "Per-row `BOOLEAN`; `NULL` outside the calendar window. See `tcal.exchanges` for "
            "codes.",
            "is trading day, exchange session, market open, london session, xlon, mic code, stock exchange calendar",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.is_trading_day(DATE '2026-12-28', 'XLON')",
                description="Is 2026-12-28 a London Stock Exchange session?",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to evaluate.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# next_trading_day(date[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _next_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.Date32Array:
    out = [None if d is None else core.next_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.date32())


class NextTradingDayFunction(ScalarFunction):
    """``next_trading_day(date)`` -- first session strictly after ``date``."""

    class Meta:
        """Function metadata."""

        name = "next_trading_day"
        description = "First trading session strictly after a date (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Next Trading Day",
            "Return the **first trading session strictly after** a given date -- the next day the "
            "market is open. This one-argument overload uses the default exchange `'XNYS'` (NYSE). "
            "The input itself is never returned even if it is a session; the search skips weekends "
            "and exchange holidays. Returns `DATE` per row (`NULL` date -> `NULL`); `NULL` if the "
            "next session falls outside the calendar's coverage window. Use it to roll a date "
            "forward to the next market open. For other markets use the exchange overload.",
            "## next_trading_day(date)\n\n"
            "First **NYSE trading session strictly after** `date` (exchange `'XNYS'`).\n\n"
            "Skips weekends + exchange holidays; never returns `date` itself. Per-row `DATE`. See "
            "the exchange overload and `tcal.exchanges`.",
            "next trading day, next session, roll forward, following market day, next open, trading calendar, nyse",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.next_trading_day(DATE '2026-01-01')",
                description="Next NYSE session after New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to search relative to.")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _next_trading_day_column(date, exchange=_DEFAULT)


class NextTradingDayExchangeFunction(ScalarFunction):
    """``next_trading_day(date, exchange)`` -- next session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "next_trading_day"
        description = "First trading session strictly after a date on an exchange"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Next Trading Day On Exchange",
            "Return the **first trading session strictly after** a date. The `exchange` argument is "
            "optional and defaults to `'XNYS'` (NYSE); pass a MIC code (e.g. `'XTKS'` for Tokyo) "
            "for another market. The input "
            "date is never returned; the search skips that exchange's weekends and holidays. "
            "Returns `DATE` per row (`NULL` date -> `NULL`); `NULL` if the result is outside the "
            "calendar's coverage window. List valid codes with `tcal.exchanges`.",
            "## next_trading_day(date[, exchange])\n\n"
            "First **session strictly after** `date`; `exchange` defaults to `'XNYS'` (e.g. "
            "`'XTKS'`).\n\n"
            "Skips that exchange's weekends + holidays. Per-row `DATE`. See `tcal.exchanges`.",
            "next trading day, exchange next session, roll forward, tokyo session, xtks, next market open, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.next_trading_day(DATE '2026-01-01', 'XTKS')",
                description="Next Tokyo session after New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to search relative to.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _next_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# previous_trading_day(date[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _previous_trading_day_column(date: pa.Date32Array, *, exchange: str) -> pa.Date32Array:
    out = [None if d is None else core.previous_trading_day(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.date32())


class PreviousTradingDayFunction(ScalarFunction):
    """``previous_trading_day(date)`` -- last session strictly before ``date``."""

    class Meta:
        """Function metadata."""

        name = "previous_trading_day"
        description = "Last trading session strictly before a date (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Previous Trading Day",
            "Return the **last trading session strictly before** a given date -- the most recent "
            "day the market was open. This one-argument overload uses the default exchange "
            "`'XNYS'` (NYSE). The input itself is never returned; the search skips weekends and "
            "exchange holidays. Returns `DATE` per row (`NULL` date -> `NULL`); `NULL` if the "
            "prior session falls outside the calendar's coverage window. Use it to roll a date "
            "back to the prior market open (e.g. for as-of pricing). See the exchange overload for "
            "other markets.",
            "## previous_trading_day(date)\n\n"
            "Last **NYSE trading session strictly before** `date` (exchange `'XNYS'`).\n\n"
            "Skips weekends + holidays; never returns `date` itself. Per-row `DATE`. Handy for "
            "as-of / prior-close lookups. See the exchange overload.",
            "previous trading day, prior session, roll back, last market day, prior open, "
            "as-of date, trading calendar, nyse",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.previous_trading_day(DATE '2026-01-01')",
                description="Last NYSE session before New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to search relative to.")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _previous_trading_day_column(date, exchange=_DEFAULT)


class PreviousTradingDayExchangeFunction(ScalarFunction):
    """``previous_trading_day(date, exchange)`` -- previous session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "previous_trading_day"
        description = "Last trading session strictly before a date on an exchange"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Previous Trading Day On Exchange",
            "Return the **last trading session strictly before** a date. The `exchange` argument is "
            "optional and defaults to `'XNYS'` (NYSE); pass a MIC code (e.g. `'XLON'` for London) "
            "for another market. The "
            "input date is never returned; the search skips that exchange's weekends and holidays. "
            "Returns `DATE` per row (`NULL` date -> `NULL`); `NULL` if outside the coverage "
            "window. List valid codes with `tcal.exchanges`.",
            "## previous_trading_day(date[, exchange])\n\n"
            "Last **session strictly before** `date`; `exchange` defaults to `'XNYS'` (e.g. "
            "`'XLON'`).\n\n"
            "Skips that exchange's weekends + holidays. Per-row `DATE`. See `tcal.exchanges`.",
            "previous trading day, exchange prior session, roll back, london session, xlon, "
            "prior market open, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.previous_trading_day(DATE '2026-01-01', 'XLON')",
                description="Last London session before New Year's Day",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to search relative to.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _previous_trading_day_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# add_trading_days(date, n[, exchange]) -> DATE
# ---------------------------------------------------------------------------


def _add_trading_days_column(date: pa.Date32Array, n: pa.Int32Array, *, exchange: str) -> pa.Date32Array:
    out = [
        None if d is None or k is None else core.add_trading_days(d, int(k), exchange)
        for d, k in zip(date.to_pylist(), n.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.date32())


class AddTradingDaysFunction(ScalarFunction):
    """``add_trading_days(date, n)`` -- advance by N NYSE sessions."""

    class Meta:
        """Function metadata."""

        name = "add_trading_days"
        description = "Advance a date by N trading sessions, skipping non-sessions (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Add Trading Days",
            "Advance a date by **N trading sessions**, skipping non-session days (weekends and "
            "exchange holidays). This two-argument overload uses the default exchange `'XNYS'` "
            "(NYSE). `N` may be negative to step *backwards*; the result is always itself a "
            "trading session. Returns `DATE` per row (`NULL` date or `NULL` n -> `NULL`); `NULL` "
            "if the result falls outside the calendar's coverage window. Use it for "
            "settlement-style math (e.g. T+2). For other markets use the exchange overload.",
            "## add_trading_days(date, n)\n\n"
            "Advance `date` by **`n` NYSE trading sessions** (exchange `'XNYS'`).\n\n"
            "Skips weekends + exchange holidays; `n` can be negative. Per-row `DATE`. Use for "
            "T+N settlement math. See the exchange overload.",
            "add trading days, t+2, settlement, session offset, trade date plus, advance sessions, "
            "trading calendar, nyse",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.add_trading_days(DATE '2026-01-02', 5)",
                description="Five NYSE sessions after 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to advance from.")],
        n: Annotated[pa.Int32Array, Param(doc="Sessions to add (negative goes backwards).")],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_trading_days_column(date, n, exchange=_DEFAULT)


class AddTradingDaysExchangeFunction(ScalarFunction):
    """``add_trading_days(date, n, exchange)`` -- advance by N sessions on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "add_trading_days"
        description = "Advance a date by N trading sessions on an exchange"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Add Trading Days On Exchange",
            "Advance a date by **N trading sessions**, skipping the exchange's non-session days. "
            "The `exchange` argument is optional and defaults to `'XNYS'` (NYSE); pass a MIC code "
            "(e.g. `'XLON'`) for another market. `N` may be negative to step backwards; the result "
            "is always a trading "
            "session. Returns `DATE` per row (`NULL` inputs -> `NULL`); `NULL` if outside the "
            "calendar's coverage window. List valid codes with `tcal.exchanges`.",
            "## add_trading_days(date, n[, exchange])\n\n"
            "Advance `date` by **`n` trading sessions**; `exchange` defaults to `'XNYS'` (e.g. "
            "`'XLON'`).\n\n"
            "Skips that exchange's non-session days; `n` can be negative. Per-row `DATE`. See "
            "`tcal.exchanges`.",
            "add trading days, exchange session offset, settlement, london sessions, xlon, advance sessions, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.add_trading_days(DATE '2026-01-02', 5, 'XLON')",
                description="Five London sessions after 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to advance from.")],
        n: Annotated[pa.Int32Array, Param(doc="Sessions to add (negative goes backwards).")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.Date32Array, Returns()]:
        """Compute the result column for each input row."""
        return _add_trading_days_column(date, n, exchange=exchange)


# ---------------------------------------------------------------------------
# trading_days_between(start, end[, exchange]) -> INT
# ---------------------------------------------------------------------------


def _trading_days_between_column(start: pa.Date32Array, end: pa.Date32Array, *, exchange: str) -> pa.Int32Array:
    out = [
        None if s is None or e is None else core.trading_days_between(s, e, exchange)
        for s, e in zip(start.to_pylist(), end.to_pylist(), strict=True)
    ]
    return pa.array(out, type=pa.int32())


class TradingDaysBetweenFunction(ScalarFunction):
    """``trading_days_between(start, end)`` -- count sessions in ``[start, end)``."""

    class Meta:
        """Function metadata."""

        name = "trading_days_between"
        description = "Count trading sessions in [start, end), start inclusive (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Count Trading Days Between",
            "Count the number of **trading sessions in the half-open interval `[start, end)`** -- "
            "`start` inclusive, `end` exclusive -- skipping weekends and exchange holidays. This "
            "two-argument overload uses the default exchange `'XNYS'` (NYSE). Returns `INTEGER` per "
            "row (`NULL` if a bound is `NULL`); the count is negative if `end` precedes `start`. "
            "Use it to measure session-based durations (e.g. holding periods in trading days). For "
            "other markets use the exchange overload.",
            "## trading_days_between(start, end)\n\n"
            "Count **trading sessions in `[start, end)`** (start inclusive) for NYSE.\n\n"
            "Skips weekends + exchange holidays; negative if `end < start`. Per-row `INTEGER`. "
            "Use for session-count durations. See the exchange overload.",
            "trading days between, count sessions, session count, holding period, trading-day "
            "duration, nyse sessions, market days",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.trading_days_between(DATE '2026-01-01', DATE '2026-02-01')",
                description="NYSE sessions in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Inclusive lower bound of the span to count over.")],
        end: Annotated[pa.Date32Array, Param(doc="Exclusive upper bound of the span to count over.")],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _trading_days_between_column(start, end, exchange=_DEFAULT)


class TradingDaysBetweenExchangeFunction(ScalarFunction):
    """``trading_days_between(start, end, exchange)`` -- count on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "trading_days_between"
        description = "Count trading sessions in [start, end) on an exchange (start inclusive)"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Count Trading Days Between On Exchange",
            "Count the number of **trading sessions in `[start, end)`** -- "
            "`start` inclusive, `end` exclusive -- skipping the exchange's weekends and holidays. "
            "The `exchange` argument is optional and defaults to `'XNYS'` (NYSE); pass a MIC code "
            "(e.g. `'XLON'`) for another market. Returns `INTEGER` per "
            "row (`NULL` if a bound is `NULL`); negative if `end` precedes `start`. List valid "
            "codes with `tcal.exchanges`.",
            "## trading_days_between(start, end[, exchange])\n\n"
            "Count **trading sessions in `[start, end)`**; `exchange` defaults to `'XNYS'` (e.g. "
            "`'XLON'`).\n\n"
            "Skips that exchange's weekends + holidays; negative if reversed. Per-row `INTEGER`. "
            "See `tcal.exchanges`.",
            "trading days between, exchange session count, holding period, london sessions, xlon, "
            "market days, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.trading_days_between(DATE '2026-01-01', DATE '2026-02-01', 'XLON')",
                description="London sessions in January 2026",
            ),
        ]

    @classmethod
    def compute(
        cls,
        start: Annotated[pa.Date32Array, Param(doc="Inclusive lower bound of the span to count over.")],
        end: Annotated[pa.Date32Array, Param(doc="Exclusive upper bound of the span to count over.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.Int32Array, Returns()]:
        """Compute the result column for each input row."""
        return _trading_days_between_column(start, end, exchange=exchange)


# ---------------------------------------------------------------------------
# market_open / market_close(date[, exchange]) -> TIMESTAMPTZ (UTC)
# ---------------------------------------------------------------------------


def _market_open_column(date: pa.Date32Array, *, exchange: str) -> pa.TimestampArray:
    out = [None if d is None else core.market_open(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=_TZ_TS)


def _market_close_column(date: pa.Date32Array, *, exchange: str) -> pa.TimestampArray:
    out = [None if d is None else core.market_close(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=_TZ_TS)


class MarketOpenFunction(ScalarFunction):
    """``market_open(date)`` -- UTC open instant, or NULL if not a session."""

    class Meta:
        """Function metadata."""

        name = "market_open"
        description = "UTC market-open instant for a date, NULL if not a session (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Market Open Instant",
            "Return the **market-open instant** for a date as a UTC `TIMESTAMPTZ`, or `NULL` if the "
            "date is not a trading session. This one-argument overload uses the default exchange "
            "`'XNYS'` (NYSE, which opens 14:30 UTC during standard time). The instant is timezone-"
            "aware (UTC) so it compares correctly regardless of the session's local timezone or "
            "DST. Returns `NULL` for non-sessions and for dates outside the calendar's coverage "
            "window. For other markets use `market_open(date, exchange)`; see `tcal.exchanges`.",
            "## market_open(date)\n\n"
            "**UTC open instant** (`TIMESTAMPTZ`) for an NYSE session, else `NULL`.\n\n"
            "Timezone-aware (UTC), DST-correct. `NULL` for non-sessions / out-of-window dates. See "
            "the exchange overload and `market_close`.",
            "market open, opening bell, session open, trading hours, open time, utc timestamp, nyse open, market hours",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.market_open(DATE '2026-01-02')",
                description="NYSE open on 2026-01-02 (14:30 UTC)",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day of the trading session.")],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_open_column(date, exchange=_DEFAULT)


class MarketOpenExchangeFunction(ScalarFunction):
    """``market_open(date, exchange)`` -- UTC open instant on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "market_open"
        description = "UTC market-open instant for a date on an exchange, NULL if not a session"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Market Open Instant On Exchange",
            "Return the **market-open instant** for a date as a UTC "
            "`TIMESTAMPTZ`, or `NULL` if it is not a session. The `exchange` argument is optional "
            "and defaults to `'XNYS'` (NYSE); pass a MIC code "
            "(e.g. `'XLON'`) for another market. The instant is timezone-aware (UTC) so it is "
            "directly comparable across exchanges and DST. Returns `NULL` for non-sessions and "
            "out-of-window dates. List valid codes with `tcal.exchanges`.",
            "## market_open(date[, exchange])\n\n"
            "**UTC open instant** (`TIMESTAMPTZ`) for a session, else `NULL`; `exchange` defaults "
            "to `'XNYS'` (e.g. `'XLON'`).\n\n"
            "Timezone-aware (UTC), DST-correct. See `tcal.exchanges` and `market_close`.",
            "market open, exchange opening, session open, london open, xlon, trading hours, utc timestamp, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.market_open(DATE '2026-01-02', 'XLON')",
                description="London open on 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day of the trading session.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_open_column(date, exchange=exchange)


class MarketCloseFunction(ScalarFunction):
    """``market_close(date)`` -- UTC close instant, or NULL if not a session."""

    class Meta:
        """Function metadata."""

        name = "market_close"
        description = "UTC market-close instant for a date, NULL if not a session (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Market Close Instant",
            "Return the **market-close instant** for a date as a UTC `TIMESTAMPTZ`, or `NULL` if "
            "the date is not a trading session. This one-argument overload uses the default "
            "exchange `'XNYS'` (NYSE). Crucially, the close reflects **early-close** sessions: "
            "half-days such as the day after US Thanksgiving close early (18:00 UTC instead of "
            "21:00), and this function returns the actual early-close instant. Timezone-aware "
            "(UTC), DST-correct. Returns `NULL` for non-sessions / out-of-window dates. Pair with "
            "`is_early_close` to detect half-days; see the exchange overload for other markets.",
            "## market_close(date)\n\n"
            "**UTC close instant** (`TIMESTAMPTZ`) for an NYSE session, else `NULL`.\n\n"
            "Reflects **early closes** (e.g. day after Thanksgiving). Timezone-aware (UTC). See "
            "`is_early_close`, `market_open`, and the exchange overload.",
            "market close, closing bell, session close, early close, half day, close time, "
            "utc timestamp, nyse close, trading hours",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.market_close(DATE '2026-11-27')",
                description="NYSE early close the day after Thanksgiving (18:00 UTC)",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day of the trading session.")],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_close_column(date, exchange=_DEFAULT)


class MarketCloseExchangeFunction(ScalarFunction):
    """``market_close(date, exchange)`` -- UTC close instant on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "market_close"
        description = "UTC market-close instant for a date on an exchange, NULL if not a session"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Market Close Instant On Exchange",
            "Return the **market-close instant** for a date, as a UTC "
            "`TIMESTAMPTZ`, or `NULL` if it is not a session. The `exchange` argument is optional "
            "and defaults to `'XNYS'` (NYSE); pass a MIC code "
            "(e.g. `'XLON'`) for another market. The close reflects early-close half-days for "
            "that exchange. Timezone-aware (UTC), DST-correct, directly comparable across "
            "exchanges. Returns `NULL` for non-sessions / out-of-window dates. List valid codes "
            "with `tcal.exchanges`.",
            "## market_close(date[, exchange])\n\n"
            "**UTC close instant** (`TIMESTAMPTZ`) for a session, else `NULL`; `exchange` defaults "
            "to `'XNYS'` (e.g. `'XLON'`).\n\n"
            "Reflects that exchange's early closes; timezone-aware (UTC). See `tcal.exchanges` "
            "and `is_early_close`.",
            "market close, exchange closing, session close, early close, london close, xlon, "
            "close time, utc timestamp, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.market_close(DATE '2026-01-02', 'XLON')",
                description="London close on 2026-01-02",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day of the trading session.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.TimestampArray, Returns(arrow_type=_TZ_TS)]:
        """Compute the result column for each input row."""
        return _market_close_column(date, exchange=exchange)


# ---------------------------------------------------------------------------
# is_early_close(date[, exchange]) -> BOOLEAN
# ---------------------------------------------------------------------------


def _is_early_close_column(date: pa.Date32Array, *, exchange: str) -> pa.BooleanArray:
    out = [None if d is None else core.is_early_close(d, exchange) for d in date.to_pylist()]
    return pa.array(out, type=pa.bool_())


class IsEarlyCloseFunction(ScalarFunction):
    """``is_early_close(date)`` -- True if the session closes early."""

    class Meta:
        """Function metadata."""

        name = "is_early_close"
        description = "True if a date is a session that closes early (exchange 'XNYS')"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Is Early-Close Session",
            "Test whether a date is a **trading session that closes early** (a half-day). This "
            "one-argument overload uses the default exchange `'XNYS'` (NYSE), where e.g. the day "
            "after Thanksgiving and Christmas Eve close early. Returns `BOOLEAN` per row: `true` "
            "only for sessions with a shortened close, `false` for normal sessions, and `NULL` for "
            "non-session days or dates outside the calendar's coverage window. Use it to flag "
            "half-days in a schedule. For other markets use the exchange overload.",
            "## is_early_close(date)\n\n"
            "True if `date` is an **early-close (half-day) NYSE session** (exchange `'XNYS'`).\n\n"
            "`false` for normal sessions, `NULL` for non-sessions. Per-row `BOOLEAN`. Pairs with "
            "`market_close`. See the exchange overload.",
            "is early close, half day, early close, shortened session, abbreviated trading, "
            "thanksgiving close, christmas eve, trading hours",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.is_early_close(DATE '2026-11-27')",
                description="The day after US Thanksgiving is an early close",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to evaluate.")],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_early_close_column(date, exchange=_DEFAULT)


class IsEarlyCloseExchangeFunction(ScalarFunction):
    """``is_early_close(date, exchange)`` -- early-close session on ``exchange``."""

    class Meta:
        """Function metadata."""

        name = "is_early_close"
        description = "True if a date is a session that closes early on an exchange"
        categories = ["calendar", "trading"]
        tags = object_tags(
            "Is Early-Close Session On Exchange",
            "Test whether a date is an **early-close (half-day) trading session**. The `exchange` "
            "argument is optional and defaults to `'XNYS'` (NYSE); pass a MIC code (e.g. `'XLON'`) "
            "for another market -- e.g. Christmas Eve "
            "is an early close on the London Stock Exchange. Returns `BOOLEAN` per row: `true` for "
            "shortened sessions, `false` for normal sessions, `NULL` for non-sessions or "
            "out-of-window dates. List valid codes with `tcal.exchanges`.",
            "## is_early_close(date[, exchange])\n\n"
            "True if `date` is an **early-close session**; `exchange` defaults to `'XNYS'` (e.g. "
            "`'XLON'`).\n\n"
            "`false` for normal sessions, `NULL` for non-sessions. Per-row `BOOLEAN`. See "
            "`tcal.exchanges` and `market_close`.",
            "is early close, half day, exchange early close, shortened session, london half day, "
            "xlon, christmas eve, mic code",
            _SRC,
        )
        examples = [
            FunctionExample(
                sql="SELECT tcal.main.is_early_close(DATE '2026-12-24', 'XLON')",
                description="Christmas Eve is an early close on the LSE",
            ),
        ]

    @classmethod
    def compute(
        cls,
        date: Annotated[pa.Date32Array, Param(doc="Calendar day to evaluate.")],
        exchange: Annotated[str, ConstParam(_EXCHANGE_DOC, choices=_EXCHANGE_CHOICES)],
    ) -> Annotated[pa.BooleanArray, Returns()]:
        """Compute the result column for each input row."""
        return _is_early_close_column(date, exchange=exchange)


SCALAR_FUNCTIONS: list[type] = [
    IsTradingDayFunction,
    IsTradingDayExchangeFunction,
    NextTradingDayFunction,
    NextTradingDayExchangeFunction,
    PreviousTradingDayFunction,
    PreviousTradingDayExchangeFunction,
    AddTradingDaysFunction,
    AddTradingDaysExchangeFunction,
    TradingDaysBetweenFunction,
    TradingDaysBetweenExchangeFunction,
    MarketOpenFunction,
    MarketOpenExchangeFunction,
    MarketCloseFunction,
    MarketCloseExchangeFunction,
    IsEarlyCloseFunction,
    IsEarlyCloseExchangeFunction,
]
