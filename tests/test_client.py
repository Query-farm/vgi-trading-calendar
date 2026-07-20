"""End-to-end tests driving the worker over the real VGI client/RPC stack.

These spawn ``trading_calendar_worker.py`` as a subprocess via
``vgi.client.Client`` and exercise the wire protocol, exactly as DuckDB would
after ``ATTACH``. They are slower than the in-process harness tests, so we keep
coverage here to one representative scalar and the set-returning table
functions.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pyarrow as pa
import pytest
from vgi import Arguments
from vgi.client import Client

_WORKER = str(Path(__file__).resolve().parent.parent / "trading_calendar_worker.py")


@pytest.fixture(scope="module")
def client() -> Client:
    with Client(f"uv run {_WORKER}") as c:
        yield c


def test_next_trading_day_scalar(client: Client) -> None:
    batch = pa.RecordBatch.from_pydict({"d": pa.array([dt.date(2026, 1, 1)], type=pa.date32())})
    results = list(
        client.scalar_function(
            function_name="next_trading_day",
            input=iter([batch]),
            arguments=Arguments(positional=()),
        )
    )
    assert results[0]["result"].to_pylist() == [dt.date(2026, 1, 2)]


def test_trading_sessions_table_function(client: Client) -> None:
    results = list(
        client.table_function(
            function_name="trading_sessions",
            arguments=Arguments(
                positional=(
                    pa.scalar(dt.date(2026, 1, 1), type=pa.date32()),
                    pa.scalar(dt.date(2026, 1, 31), type=pa.date32()),
                ),
                named={"exchange": pa.scalar("XNYS")},
            ),
        )
    )
    table = pa.Table.from_batches(results)
    # 20 NYSE sessions in January 2026; New Year's Day is excluded.
    assert table.num_rows == 20
    assert dt.date(2026, 1, 1) not in table.column("session").to_pylist()


def test_trading_schedule_marks_early_close(client: Client) -> None:
    results = list(
        client.table_function(
            function_name="trading_schedule",
            arguments=Arguments(
                positional=(
                    pa.scalar(dt.date(2026, 11, 27), type=pa.date32()),
                    pa.scalar(dt.date(2026, 11, 27), type=pa.date32()),
                ),
            ),
        )
    )
    table = pa.Table.from_batches(results)
    assert table.num_rows == 1
    assert table.column("is_early_close").to_pylist() == [True]
