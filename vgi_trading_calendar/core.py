"""Pure trading / exchange-calendar math.

No Arrow or VGI dependency lives here -- just :mod:`exchange_calendars` (the
maintained successor to Quantopian's ``trading_calendars``) over ``datetime``.
Keeping the math in one importable, side-effect-free module means it can be
unit-tested directly and reused by the Arrow-facing adapters in
:mod:`vgi_trading_calendar.scalars` and :mod:`vgi_trading_calendar.tables`.

An *exchange* is selected by its ISO-10383 MIC code (default ``"XNYS"`` -- the
New York Stock Exchange). ``tcal.exchanges`` lists every supported code
(``XNAS`` Nasdaq, ``XLON`` London, ``XTKS`` Tokyo, ...).

A *session* is a trading day. ``market_open`` / ``market_close`` are timezone
aware **UTC** instants. Coverage is the library's default window (roughly two
decades back to about a year ahead -- future exchange holidays are only defined
so far); a date outside that window resolves to ``NULL`` / no rows rather than
raising.
"""

from __future__ import annotations

import datetime as _dt
import functools
from typing import cast

import exchange_calendars as _xcals
import pandas as _pd

DEFAULT_EXCHANGE = "XNYS"


class UnknownExchangeError(ValueError):
    """Raised when an exchange code is not a known calendar."""


@functools.lru_cache(maxsize=64)
def _calendar(exchange: str) -> _xcals.ExchangeCalendar:
    """A cached :class:`exchange_calendars.ExchangeCalendar` for ``exchange``.

    One calendar object per code per worker process; it caches its session
    index internally, so repeated lookups across many rows stay cheap.
    """
    code = exchange.upper()
    try:
        return _xcals.get_calendar(code)
    except _xcals.errors.InvalidCalendarName as exc:
        raise UnknownExchangeError(
            f"Unknown exchange calendar {exchange!r}. Call tcal.exchanges for valid codes."
        ) from exc


def _ts(date: _dt.date) -> _pd.Timestamp:
    """A tz-naive midnight ``Timestamp`` session label for ``date``."""
    return _pd.Timestamp(date.year, date.month, date.day)


def _sessions(exchange: str) -> _pd.DatetimeIndex:
    return _calendar(exchange).sessions


def _to_utc_dt(ts: _pd.Timestamp) -> _dt.datetime:
    """A timezone-aware UTC :class:`datetime` for a (UTC) pandas ``Timestamp``."""
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    # pandas is untyped, so to_pydatetime() is inferred as Any under --strict.
    return cast("_dt.datetime", ts.tz_convert("UTC").to_pydatetime())


def list_exchanges() -> list[str]:
    """Every supported exchange MIC code, sorted."""
    return sorted(_xcals.get_calendar_names())


def is_trading_day(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> bool:
    """True if ``date`` is a trading session on ``exchange``.

    Dates outside the calendar's coverage window are ``False``.
    """
    sess = _sessions(exchange)
    ts = _ts(date)
    if len(sess) == 0 or ts < sess[0] or ts > sess[-1]:
        return False
    return bool(_calendar(exchange).is_session(ts))


def next_trading_day(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> _dt.date | None:
    """The first trading session strictly **after** ``date`` (``None`` if none known)."""
    sess = _sessions(exchange)
    i = int(sess.searchsorted(_ts(date), side="right"))
    return sess[i].date() if i < len(sess) else None


def previous_trading_day(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> _dt.date | None:
    """The last trading session strictly **before** ``date`` (``None`` if none known)."""
    sess = _sessions(exchange)
    i = int(sess.searchsorted(_ts(date), side="left"))
    return sess[i - 1].date() if i > 0 else None


def add_trading_days(date: _dt.date, n: int, exchange: str = DEFAULT_EXCHANGE) -> _dt.date | None:
    """Advance ``date`` by ``n`` trading sessions (negative ``n`` goes backwards).

    ``n == 0`` returns ``date`` unchanged even if it is not itself a session.
    Otherwise the result is the ``|n|``-th session strictly after (``n > 0``) or
    before (``n < 0``) ``date``. ``None`` if that session is outside the
    calendar's coverage window.
    """
    if n == 0:
        return date
    sess = _sessions(exchange)
    ts = _ts(date)
    j = int(sess.searchsorted(ts, side="right")) + n - 1 if n > 0 else int(sess.searchsorted(ts, side="left")) + n
    return sess[j].date() if 0 <= j < len(sess) else None


def trading_days_between(start: _dt.date, end: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> int:
    """Count trading sessions in ``[start, end)`` -- half-open, ``start`` inclusive.

    ``trading_days_between(d, d)`` is ``0``. If ``end`` is before ``start`` the
    count is negative (sessions counted backwards), mirroring how a date
    difference behaves.
    """
    if start == end:
        return 0
    sess = _sessions(exchange)
    sign = 1 if end > start else -1
    lo, hi = (start, end) if end > start else (end, start)
    count = int(sess.searchsorted(_ts(hi), side="left")) - int(sess.searchsorted(_ts(lo), side="left"))
    return sign * count


def market_open(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> _dt.datetime | None:
    """UTC market-open instant for ``date``, or ``None`` if it is not a session."""
    if not is_trading_day(date, exchange):
        return None
    return _to_utc_dt(_calendar(exchange).session_open(_ts(date)))


def market_close(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> _dt.datetime | None:
    """UTC market-close instant for ``date``, or ``None`` if it is not a session."""
    if not is_trading_day(date, exchange):
        return None
    return _to_utc_dt(_calendar(exchange).session_close(_ts(date)))


def is_early_close(date: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> bool:
    """True if ``date`` is a session that closes early (e.g. the day after US Thanksgiving)."""
    if not is_trading_day(date, exchange):
        return False
    return _ts(date) in _calendar(exchange).early_closes


def trading_sessions_in_range(start: _dt.date, end: _dt.date, exchange: str = DEFAULT_EXCHANGE) -> list[_dt.date]:
    """Every trading session in the inclusive range ``[start, end]``, ascending."""
    if end < start:
        return []
    sess = _sessions(exchange)
    lo = int(sess.searchsorted(_ts(start), side="left"))
    hi = int(sess.searchsorted(_ts(end), side="right"))
    return [d.date() for d in sess[lo:hi]]


def trading_schedule(
    start: _dt.date, end: _dt.date, exchange: str = DEFAULT_EXCHANGE
) -> list[tuple[_dt.date, _dt.datetime, _dt.datetime, bool]]:
    """``(session, market_open, market_close, is_early_close)`` per session in ``[start, end]``."""
    cal = _calendar(exchange)
    early = set(cal.early_closes)
    rows: list[tuple[_dt.date, _dt.datetime, _dt.datetime, bool]] = []
    for d in trading_sessions_in_range(start, end, exchange):
        ts = _ts(d)
        rows.append((d, _to_utc_dt(cal.session_open(ts)), _to_utc_dt(cal.session_close(ts)), ts in early))
    return rows
