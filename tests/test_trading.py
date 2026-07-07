"""Unit + edge-case tests for the pure trading / exchange-calendar math.

These exercise the pure :mod:`vgi_trading_calendar.trading` math directly (no
Arrow / RPC). The end-to-end ATTACH+SELECT path is covered by
``test/sql/trading.test``.
"""

from __future__ import annotations

import datetime as dt

import pytest

from vgi_trading_calendar import trading


class TestIsTradingDay:
    def test_regular_session(self) -> None:
        assert trading.is_trading_day(dt.date(2026, 1, 2)) is True  # Friday

    def test_weekend_is_not_a_session(self) -> None:
        assert trading.is_trading_day(dt.date(2026, 1, 3)) is False  # Saturday

    def test_market_holiday_is_not_a_session(self) -> None:
        assert trading.is_trading_day(dt.date(2026, 1, 1)) is False  # New Year's Day

    def test_other_exchange(self) -> None:
        # 2026-07-03 is a US holiday-observed day but a normal LSE session.
        assert trading.is_trading_day(dt.date(2026, 7, 3), "XLON") is True
        assert trading.is_trading_day(dt.date(2026, 7, 3), "XNYS") is False

    def test_out_of_window_is_false_not_error(self) -> None:
        assert trading.is_trading_day(dt.date(1800, 1, 2)) is False


class TestNavigation:
    def test_next_skips_holiday_and_weekend(self) -> None:
        assert trading.next_trading_day(dt.date(2026, 1, 1)) == dt.date(2026, 1, 2)

    def test_previous_is_strict(self) -> None:
        # Strictly before, even when the date itself is a session.
        assert trading.previous_trading_day(dt.date(2026, 1, 2)) == dt.date(2025, 12, 31)

    def test_add_positive(self) -> None:
        assert trading.add_trading_days(dt.date(2026, 1, 2), 5) == dt.date(2026, 1, 9)

    def test_add_negative(self) -> None:
        assert trading.add_trading_days(dt.date(2026, 1, 2), -1) == dt.date(2025, 12, 31)

    def test_add_zero_is_identity(self) -> None:
        # n == 0 returns the input unchanged even if it is not a session.
        assert trading.add_trading_days(dt.date(2026, 1, 1), 0) == dt.date(2026, 1, 1)

    def test_between_half_open(self) -> None:
        assert trading.trading_days_between(dt.date(2026, 1, 1), dt.date(2026, 2, 1)) == 20

    def test_between_same_day_is_zero(self) -> None:
        assert trading.trading_days_between(dt.date(2026, 1, 2), dt.date(2026, 1, 2)) == 0

    def test_between_reversed_is_negative(self) -> None:
        fwd = trading.trading_days_between(dt.date(2026, 1, 1), dt.date(2026, 2, 1))
        rev = trading.trading_days_between(dt.date(2026, 2, 1), dt.date(2026, 1, 1))
        assert rev == -fwd


class TestHoursAndEarlyClose:
    def test_market_open_close_utc(self) -> None:
        o = trading.market_open(dt.date(2026, 1, 2))
        c = trading.market_close(dt.date(2026, 1, 2))
        assert o is not None and c is not None
        assert (o.hour, o.minute) == (14, 30)  # 09:30 ET in UTC
        assert (c.hour, c.minute) == (21, 0)  # 16:00 ET in UTC
        assert o.tzinfo is not None and c.tzinfo is not None

    def test_open_close_null_on_non_session(self) -> None:
        assert trading.market_open(dt.date(2026, 1, 1)) is None
        assert trading.market_close(dt.date(2026, 1, 1)) is None

    def test_early_close_after_thanksgiving(self) -> None:
        assert trading.is_early_close(dt.date(2026, 11, 27)) is True
        # Early close really does close earlier than a normal session.
        assert trading.market_close(dt.date(2026, 11, 27)).hour < 21  # type: ignore[union-attr]

    def test_regular_session_is_not_early_close(self) -> None:
        assert trading.is_early_close(dt.date(2026, 1, 2)) is False


class TestRangesAndDiscovery:
    def test_sessions_in_range_inclusive(self) -> None:
        days = trading.trading_sessions_in_range(dt.date(2026, 1, 1), dt.date(2026, 1, 9))
        assert days[0] == dt.date(2026, 1, 2)
        assert dt.date(2026, 1, 1) not in days  # holiday excluded
        assert all(dt.date(2026, 1, 1) <= d <= dt.date(2026, 1, 9) for d in days)

    def test_sessions_in_range_empty_when_reversed(self) -> None:
        assert trading.trading_sessions_in_range(dt.date(2026, 2, 1), dt.date(2026, 1, 1)) == []

    def test_schedule_marks_early_close(self) -> None:
        rows = trading.trading_schedule(dt.date(2026, 11, 25), dt.date(2026, 11, 30))
        by_date = {r[0]: r for r in rows}
        assert dt.date(2026, 11, 26) not in by_date  # Thanksgiving: not a session
        assert by_date[dt.date(2026, 11, 27)][3] is True  # early close flagged

    def test_list_exchanges_has_majors(self) -> None:
        codes = trading.list_exchanges()
        assert {"XNYS", "XNAS", "XLON", "XTKS"} <= set(codes)


class TestUnknownExchange:
    def test_unknown_code_raises(self) -> None:
        with pytest.raises(trading.UnknownExchangeError):
            trading.is_trading_day(dt.date(2026, 1, 2), "NOPE")
