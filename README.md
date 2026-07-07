<p align="center">
  <img src="https://raw.githubusercontent.com/Query-farm/vgi/main/docs/vgi-logo.png" alt="Vector Gateway Interface (VGI)" width="320">
</p>

<p align="center"><em>A <a href="https://query.farm">Query.Farm</a> VGI worker for DuckDB.</em></p>

# Trading Calendars & Market Hours in DuckDB

> **vgi-trading-calendar** · a [Query.Farm](https://query.farm) VGI worker

[![CI](https://github.com/Query-farm/vgi-trading-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/Query-farm/vgi-trading-calendar/actions/workflows/ci.yml)

A [VGI](https://query.farm) worker that brings **stock-exchange trading
calendars** into DuckDB/SQL: is the market open on a given date, what is the next
or previous session, how many trading days lie between two dates, and what are
the market open/close hours (including early closes) — for the NYSE, Nasdaq, LSE,
Tokyo, and ~100 other exchanges. Trading calendars come from the
[`exchange-calendars`](https://pypi.org/project/exchange-calendars/) library
(Apache-2.0), the maintained successor to Quantopian's `trading_calendars`.

```sql
INSTALL vgi FROM community; LOAD vgi;
ATTACH 'tcal' (TYPE vgi, LOCATION 'uv run trading_calendar_worker.py');

-- Default exchange is 'XNYS' (NYSE):
SELECT tcal.is_trading_day(DATE '2026-01-01');            -- false (market holiday)
SELECT tcal.next_trading_day(DATE '2026-01-01');          -- 2026-01-02
SELECT tcal.add_trading_days(DATE '2026-01-02', 10);      -- 10 sessions later
SELECT tcal.trading_days_between(DATE '2026-01-01', DATE '2026-04-01');  -- Q1 sessions
SELECT tcal.market_close(DATE '2026-11-27');              -- early close after Thanksgiving
SELECT * FROM tcal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');
SELECT * FROM tcal.exchanges;                             -- ~100 supported MIC codes
```

> **Not US-centric.** The `'XNYS'` you see in examples is only a *default*. The
> trading functions cover every exchange `exchange-calendars` supports — run
> `SELECT count(*) FROM tcal.exchanges;` (roughly a hundred) or pass any MIC code
> (`'XLON'` London, `'XTKS'` Tokyo, `'XNAS'` Nasdaq, …) as the `exchange`
> argument.

## Scalars (per-row) vs. table functions (set-returning)

The split follows what the VGI SDK allows for each function shape:

* **Scalars** take **positional** arguments only and resolve overloads by
  *arity* (DuckDB's `name := value` syntax is a table-function/macro feature, not
  a scalar one). Every per-row answer — `is_trading_day`, `next_trading_day`,
  `previous_trading_day`, `add_trading_days`, `trading_days_between`,
  `market_open`, `market_close`, `is_early_close` — is a **scalar**, so it works
  inline in any projection or predicate. The optional `exchange` is an extra
  positional arity overload:

  ```sql
  SELECT is_trading_day(trade_date)             FROM fills;  -- defaults to 'XNYS'
  SELECT is_trading_day(trade_date, 'XLON')     FROM fills;  -- explicit exchange
  SELECT trade_date, add_trading_days(trade_date, 1) AS t_plus_1 FROM fills;
  ```

* **Table functions** return *many* rows and therefore accept the named
  `exchange :=` argument: `trading_sessions`, `trading_schedule`.

  ```sql
  SELECT * FROM tcal.trading_sessions(DATE '2026-01-01', DATE '2026-01-31', exchange := 'XLON');
  SELECT * FROM tcal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');
  ```

## Function catalog

| Function | Form | Signature | Returns |
| --- | --- | --- | --- |
| `is_trading_day` | scalar | `(date DATE[, exchange])` | `BOOLEAN` |
| `next_trading_day` | scalar | `(date DATE[, exchange])` | `DATE` (NULL past the window) |
| `previous_trading_day` | scalar | `(date DATE[, exchange])` | `DATE` (NULL past the window) |
| `add_trading_days` | scalar | `(date DATE, n INT[, exchange])` | `DATE` |
| `trading_days_between` | scalar | `(start DATE, end DATE[, exchange])` | `INT` |
| `market_open` | scalar | `(date DATE[, exchange])` | `TIMESTAMPTZ` (UTC, NULL if not a session) |
| `market_close` | scalar | `(date DATE[, exchange])` | `TIMESTAMPTZ` (UTC, NULL if not a session) |
| `is_early_close` | scalar | `(date DATE[, exchange])` | `BOOLEAN` |
| `trading_sessions` | table | `(start DATE, end DATE, exchange := 'XNYS')` | `(date DATE)` |
| `trading_schedule` | table | `(start DATE, end DATE, exchange := 'XNYS')` | `(session DATE, market_open TIMESTAMPTZ, market_close TIMESTAMPTZ, is_early_close BOOLEAN)` |
| `exchanges` | table | `()` | `(code VARCHAR)` |

The `exchange` default is `'XNYS'` (NYSE). Discover valid MIC codes with
`SELECT * FROM tcal.exchanges`.

## Trading / exchange calendars

Trading functions answer "is the market open, and when?" for any of the ~100
exchanges in [`exchange-calendars`](https://pypi.org/project/exchange-calendars/)
— NYSE (`XNYS`, the default), Nasdaq (`XNAS`), London (`XLON`), Tokyo (`XTKS`),
and more (`SELECT * FROM tcal.exchanges`). A **session** is a trading day;
`market_open` / `market_close` are timezone-aware **UTC** instants, and
`is_early_close` flags shortened sessions (e.g. the day after US Thanksgiving).

```sql
-- align fills to the next session and tag end-of-day vs intraday
SELECT id, trade_ts,
       next_trading_day(trade_ts::DATE)                       AS settles_on,
       trade_ts >= market_close(trade_ts::DATE, 'XNYS')       AS after_hours
FROM fills;

-- the trading schedule around a holiday week (note the early close)
SELECT * FROM tcal.trading_schedule(DATE '2026-11-25', DATE '2026-11-30');

-- count NYSE sessions in a quarter (half-open [start, end))
SELECT trading_days_between(DATE '2026-01-01', DATE '2026-04-01');
```

`trading_days_between(start, end)` counts the half-open range `[start, end)`
(`start` inclusive, `end` exclusive); a reversed range yields a negative count.
`add_trading_days(date, 0)` returns `date` unchanged even if it is not itself a
session.

Coverage is the `exchange-calendars` default window (roughly two decades back to
about a year ahead — future market holidays are only defined so far); a date
outside that window resolves to `NULL` / no rows rather than erroring.

## Companion workers

`vgi-trading-calendar` is the market-hours half of a small scheduling family:

- [vgi-calendar](https://github.com/Query-farm/vgi-calendar) — public holidays
  for hundreds of countries, business-day arithmetic, ISO week labels, and
  RFC-5545 (RRULE) recurrence expansion.
- [vgi-crontimes](https://github.com/Query-farm/vgi-crontimes) — cron-style
  firing math (`0 9 * * *` → next fire times).

## Dependencies & licensing

| Component | License |
| --- | --- |
| `vgi-trading-calendar` (this worker) | MIT |
| [`exchange-calendars`](https://pypi.org/project/exchange-calendars/) | Apache-2.0 |
| [`vgi-python`](https://github.com/Query-farm/vgi-python) | Query Farm Source-Available |

Trading-calendar definitions are only as complete as the `exchange-calendars`
library's coverage for a given exchange and year; consult its docs for the
authoritative support matrix. (`exchange-calendars` pulls in `pandas` + `numpy`,
so this worker is heavier than a pure-`datetime` one.)

## Local development

```sh
uv sync --all-extras     # create .venv with vgi-python + exchange-calendars + dev tools
make test                # pytest (unit + integration) + SQL end-to-end
make test-unit           # pytest only
make test-sql            # DuckDB sqllogictest files via haybarn-unittest
uv run ruff check .      # lint
uv run mypy vgi_trading_calendar/
```

`tests/test_trading.py` covers the pure trading math (including error / edge
cases); `tests/test_scalars.py` and `tests/test_client.py` spawn
`trading_calendar_worker.py` over the VGI client/RPC stack exactly as DuckDB
would after `ATTACH`. The `test/sql/*.test` files are DuckDB sqllogictest cases
run by [`haybarn-unittest`](https://pypi.org/project/haybarn-unittest/)
(`uv tool install haybarn-unittest`) against a real `ATTACH` + `SELECT`.

## Layout

```
trading_calendar_worker.py   entry point; assembles the `tcal` catalog (inline uv script metadata)
Makefile                     test / test-unit / test-sql targets
vgi_trading_calendar/
  trading.py                 pure trading-calendar math over exchange-calendars (no Arrow/VGI)
  trading_scalars.py         per-row trading scalars: is_trading_day, market_open/close, ...
  trading_tables.py          trading tables: trading_sessions, trading_schedule, exchanges
  schema_utils.py            Arrow field/comment helpers
  meta.py                    per-object discovery/description metadata helpers
tests/
  harness.py                 in-process bind→init→process driver
  test_trading.py            pure-math unit + error/edge tests
  test_scalars.py            per-row scalar overloads via vgi.client.Client
  test_client.py             end-to-end scalar + table tests via vgi.client.Client
test/sql/
  *.test                     DuckDB sqllogictest end-to-end cases (haybarn-unittest)
```

---

## Authorship & License

Written by [Query.Farm](https://query.farm).

Copyright 2026 Query Farm LLC - https://query.farm
