"""Composed examples are published both schema-wide and on their driving object."""

from __future__ import annotations

import json

from vgi_trading_calendar import composed, worker
from vgi_trading_calendar.tables import TradingScheduleFunction, TradingSessionsFunction


def _pairs(tag: str) -> list[tuple[str, str]]:
    return [(e["description"], e["sql"]) for e in json.loads(tag)]


def test_composed_examples_in_schema_list() -> None:
    schema_examples = _pairs(worker._SCHEMA_EXAMPLE_QUERIES)
    for ex in composed.COMPOSED_EXAMPLES:
        assert (ex.description, ex.sql) in schema_examples


def test_composed_examples_in_first_five_of_driving_object() -> None:
    drivers = {
        TradingSessionsFunction: [composed.NYSE_OPEN_LONDON_CLOSED, composed.T1_SETTLEMENT_THANKSGIVING_WEEK],
        TradingScheduleFunction: [composed.EARLY_CLOSE_NEXT_OPEN, composed.TRANSATLANTIC_OVERLAP_DST],
    }
    for fn, examples in drivers.items():
        first_five = _pairs(fn.Meta.tags["vgi.example_queries"])[:5]
        for ex in examples:
            assert (ex.description, ex.sql) in first_five
    covered = {ex.sql for exs in drivers.values() for ex in exs}
    assert covered == {ex.sql for ex in composed.COMPOSED_EXAMPLES}


def test_schema_example_queries_within_lint_limit() -> None:
    assert len(worker._SCHEMA_EXAMPLE_QUERIES) <= 8000
