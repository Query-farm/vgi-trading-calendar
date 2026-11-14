"""Unit + edge-case tests for the pure trading / exchange-calendar math.

These exercise the pure :mod:`vgi_trading_calendar.core` math directly (no
Arrow / RPC). The end-to-end ATTACH+SELECT path is covered by
``test/sql/trading.test``.
"""

from __future__ import annotations

import datetime as dt

import pytest

from vgi_trading_calendar import core


class TestIsTradingDay:
    def test_regular_session(self) -> None:
        assert core.is_trading_day(dt.date(2026, 1, 2)) is True  # Friday

    def test_weekend_is_not_a_session(self) -> None:
        assert core.is_trading_day(dt.date(2026, 1, 3)) is False  # Saturday

    def test_market_holiday_is_not_a_session(self) -> None:
        assert core.is_trading_day(dt.date(2026, 1, 1)) is False  # New Year's Day

    def test_other_exchange(self) -> None:
        # 2026-07-03 is a US holiday-observed day but a normal LSE session.
        assert core.is_trading_day(dt.date(2026, 7, 3), "XLON") is True
        assert core.is_trading_day(dt.date(2026, 7, 3), "XNYS") is False

    def test_out_of_window_is_none_not_false(self) -> None:
        # No session data out there: an ordinary weekday must not read as "closed".
        assert core.is_trading_day(dt.date(1800, 1, 2)) is None
        assert core.is_trading_day(_far_future()) is None


def _far_future() -> dt.date:
    """A weekday well past the coverage window (which ends ~1 year ahead)."""
    last = core._sessions("XNYS")[-1].date()
    d = last + dt.timedelta(days=400)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


class TestCoverageWindow:
    def test_navigation_outside_window_is_none(self) -> None:
        first = core._sessions("XNYS")[0].date()
        assert core.next_trading_day(first - dt.timedelta(days=30)) is None
        assert core.previous_trading_day(_far_future()) is None
        assert core.add_trading_days(_far_future(), -1) is None
        assert core.add_trading_days(dt.date(1800, 1, 2), 1) is None

    def test_previous_from_day_after_last_session(self) -> None:
        last = core._sessions("XNYS")[-1].date()
        assert core.previous_trading_day(last + dt.timedelta(days=1)) == last

    def test_count_leaving_window_is_none(self) -> None:
        assert core.trading_days_between(dt.date(2026, 1, 2), _far_future()) is None
        assert core.trading_days_between(_far_future(), dt.date(2026, 1, 2)) is None
        assert core.trading_days_between(dt.date(1800, 1, 2), dt.date(2026, 1, 2)) is None

    def test_count_up_to_day_after_last_session(self) -> None:
        sess = core._sessions("XNYS")
        last = sess[-1].date()
        assert core.trading_days_between(sess[-3].date(), last + dt.timedelta(days=1)) == 3

    def test_early_close_outside_window_is_none(self) -> None:
        assert core.is_early_close(_far_future()) is None


class TestNavigation:
    def test_next_skips_holiday_and_weekend(self) -> None:
        assert core.next_trading_day(dt.date(2026, 1, 1)) == dt.date(2026, 1, 2)

    def test_previous_is_strict(self) -> None:
        # Strictly before, even when the date itself is a session.
        assert core.previous_trading_day(dt.date(2026, 1, 2)) == dt.date(2025, 12, 31)

    def test_add_positive(self) -> None:
        assert core.add_trading_days(dt.date(2026, 1, 2), 5) == dt.date(2026, 1, 9)

    def test_add_negative(self) -> None:
        assert core.add_trading_days(dt.date(2026, 1, 2), -1) == dt.date(2025, 12, 31)

    def test_add_zero_is_identity(self) -> None:
        # n == 0 returns the input unchanged even if it is not a session.
        assert core.add_trading_days(dt.date(2026, 1, 1), 0) == dt.date(2026, 1, 1)

    def test_between_half_open(self) -> None:
        assert core.trading_days_between(dt.date(2026, 1, 1), dt.date(2026, 2, 1)) == 20

    def test_between_same_day_is_zero(self) -> None:
        assert core.trading_days_between(dt.date(2026, 1, 2), dt.date(2026, 1, 2)) == 0

    def test_between_reversed_is_negative(self) -> None:
        fwd = core.trading_days_between(dt.date(2026, 1, 1), dt.date(2026, 2, 1))
        rev = core.trading_days_between(dt.date(2026, 2, 1), dt.date(2026, 1, 1))
        assert rev == -fwd


class TestHoursAndEarlyClose:
    def test_market_open_close_utc(self) -> None:
        o = core.market_open(dt.date(2026, 1, 2))
        c = core.market_close(dt.date(2026, 1, 2))
        assert o is not None and c is not None
        assert (o.hour, o.minute) == (14, 30)  # 09:30 ET in UTC
        assert (c.hour, c.minute) == (21, 0)  # 16:00 ET in UTC
        assert o.tzinfo is not None and c.tzinfo is not None

    def test_open_close_null_on_non_session(self) -> None:
        assert core.market_open(dt.date(2026, 1, 1)) is None
        assert core.market_close(dt.date(2026, 1, 1)) is None

    def test_early_close_after_thanksgiving(self) -> None:
        assert core.is_early_close(dt.date(2026, 11, 27)) is True
        # Early close really does close earlier than a normal session.
        assert core.market_close(dt.date(2026, 11, 27)).hour < 21  # type: ignore[union-attr]

    def test_regular_session_is_not_early_close(self) -> None:
        assert core.is_early_close(dt.date(2026, 1, 2)) is False

    def test_non_session_early_close_is_none(self) -> None:
        assert core.is_early_close(dt.date(2026, 1, 3)) is None  # Saturday


class TestRangesAndDiscovery:
    def test_sessions_in_range_inclusive(self) -> None:
        days = core.trading_sessions_in_range(dt.date(2026, 1, 1), dt.date(2026, 1, 9))
        assert days[0] == dt.date(2026, 1, 2)
        assert dt.date(2026, 1, 1) not in days  # holiday excluded
        assert all(dt.date(2026, 1, 1) <= d <= dt.date(2026, 1, 9) for d in days)

    def test_sessions_in_range_empty_when_reversed(self) -> None:
        assert core.trading_sessions_in_range(dt.date(2026, 2, 1), dt.date(2026, 1, 1)) == []

    def test_schedule_marks_early_close(self) -> None:
        rows = core.trading_schedule(dt.date(2026, 11, 25), dt.date(2026, 11, 30))
        by_date = {r[0]: r for r in rows}
        assert dt.date(2026, 11, 26) not in by_date  # Thanksgiving: not a session
        assert by_date[dt.date(2026, 11, 27)][3] is True  # early close flagged

    def test_list_exchanges_has_majors(self) -> None:
        codes = core.list_exchanges()
        assert {"XNYS", "XNAS", "XLON", "XTKS"} <= set(codes)


class TestUnknownExchange:
    def test_unknown_code_raises(self) -> None:
        with pytest.raises(core.UnknownExchangeError):
            core.is_trading_day(dt.date(2026, 1, 2), "NOPE")
