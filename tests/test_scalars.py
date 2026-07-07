"""End-to-end tests for the per-row scalar trading-calendar functions.

These spawn ``trading_calendar_worker.py`` as a subprocess via
``vgi.client.Client`` and call each scalar exactly as DuckDB would after
``ATTACH``, exercising the arity overloads (``is_trading_day(date)`` /
``(date, exchange)`` and the like). The ``date`` column travels in the input
batch (a ``Param``); only the constant ``exchange`` argument goes in
``positional``.
"""

from __future__ import annotations

import datetime as dt
import sys
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest
from vgi import Arguments
from vgi.client import Client

_WORKER = str(Path(__file__).resolve().parent.parent / "trading_calendar_worker.py")


@pytest.fixture(scope="module")
def client() -> Iterator[Client]:
    # Use the current interpreter (deps already installed) and worker_limit=1 so
    # output order matches input order for deterministic per-row assertions.
    with Client(f"{sys.executable} {_WORKER}", worker_limit=1) as c:
        yield c


def _scalar(client: Client, name: str, batch: pa.RecordBatch, *, positional: list[pa.Scalar] | None = None) -> list:
    results = list(
        client.scalar_function(
            function_name=name,
            input=iter([batch]),
            arguments=Arguments(positional=positional or []),
        )
    )
    return results[0]["result"].to_pylist()


def _dates(values: list[dt.date]) -> pa.RecordBatch:
    return pa.RecordBatch.from_pydict({"d": pa.array(values, type=pa.date32())})


class TestIsTradingDay:
    def test_default_exchange(self, client: Client) -> None:
        # New Year's Day 2026 is not an NYSE session; the next weekday is.
        out = _scalar(client, "is_trading_day", _dates([dt.date(2026, 1, 1), dt.date(2026, 1, 2)]))
        assert out == [False, True]

    def test_explicit_exchange(self, client: Client) -> None:
        # 2026-07-03 is a US holiday-observed day but a normal London session.
        d = _dates([dt.date(2026, 7, 3)])
        assert _scalar(client, "is_trading_day", d, positional=[pa.scalar("XLON")]) == [True]
        assert _scalar(client, "is_trading_day", d, positional=[pa.scalar("XNYS")]) == [False]


class TestNavigation:
    def test_next_trading_day(self, client: Client) -> None:
        out = _scalar(client, "next_trading_day", _dates([dt.date(2026, 1, 1)]))
        assert out == [dt.date(2026, 1, 2)]

    def test_previous_trading_day(self, client: Client) -> None:
        out = _scalar(client, "previous_trading_day", _dates([dt.date(2026, 1, 2)]))
        assert out == [dt.date(2025, 12, 31)]

    def test_add_trading_days_two_args(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "d": pa.array([dt.date(2026, 1, 2)], type=pa.date32()),
                "n": pa.array([5], type=pa.int32()),
            }
        )
        out = _scalar(client, "add_trading_days", batch)
        assert out == [dt.date(2026, 1, 9)]

    def test_add_trading_days_three_args_exchange(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "d": pa.array([dt.date(2026, 1, 2)], type=pa.date32()),
                "n": pa.array([1], type=pa.int32()),
            }
        )
        out = _scalar(client, "add_trading_days", batch, positional=[pa.scalar("XLON")])
        assert out == [dt.date(2026, 1, 5)]  # 2026-01-03/04 is a weekend

    def test_trading_days_between(self, client: Client) -> None:
        batch = pa.RecordBatch.from_pydict(
            {
                "s": pa.array([dt.date(2026, 1, 1)], type=pa.date32()),
                "e": pa.array([dt.date(2026, 2, 1)], type=pa.date32()),
            }
        )
        out = _scalar(client, "trading_days_between", batch)
        assert out == [20]


class TestMarketHours:
    def test_is_early_close(self, client: Client) -> None:
        # Day after US Thanksgiving is an NYSE early close; a normal Friday is not.
        out = _scalar(client, "is_early_close", _dates([dt.date(2026, 11, 27), dt.date(2026, 1, 2)]))
        assert out == [True, False]

    def test_market_close_utc_instant(self, client: Client) -> None:
        out = _scalar(client, "market_close", _dates([dt.date(2026, 1, 2)]))
        assert out[0] == dt.datetime(2026, 1, 2, 21, 0, tzinfo=dt.UTC)

    def test_market_open_null_on_non_session(self, client: Client) -> None:
        out = _scalar(client, "market_open", _dates([dt.date(2026, 1, 1)]))
        assert out == [None]
