# CLAUDE.md — vgi-trading-calendar

Contributor/agent notes. User-facing docs live in `README.md`; this is the
"how it's built and where the sharp edges are" companion.

## What this is

A [VGI](https://query.farm) worker exposing **stock-exchange trading-calendar**
math to DuckDB/SQL, backed by `exchange-calendars` (Apache-2.0).
`trading_calendar_worker.py` assembles every function into one `tcal` catalog
(single `main` schema) over stdio. Split out of `vgi-calendar`, which keeps the
holiday / business-day / RFC-5545 recurrence side; `vgi-crontimes` is the sibling
cron-firing worker.

## Layout

```
trading_calendar_worker.py   repo-root stdio entry point; PEP 723 inline deps; main()
vgi_trading_calendar/
  trading.py                 pure trading-calendar math (exchange-calendars); no Arrow/VGI
  trading_scalars.py         per-row trading scalars (arity overloads, exchange default 'XNYS')
  trading_tables.py          trading_sessions / trading_schedule / exchanges()
  schema_utils.py            pa.Field comment / column-doc helper
  meta.py                    per-object discovery/description tag helpers (vgi-lint strict)
tests/                       pytest: test_trading (pure), test_scalars + test_client (Client RPC)
test/sql/*.test              haybarn-unittest sqllogictest — authoritative E2E
Makefile                     test / test-unit / test-sql / lint
```

To add a function: implement the math in `trading.py` (pure), wrap it as a scalar
or table function in the matching module, register it in
`trading_calendar_worker.py`'s `_FUNCTIONS` (and add it to `_CATEGORY_BY_NAME`).

## Coverage is broad — "US-centric" is just the default

`exchange-calendars` supports **~100** exchange calendars; every trading function
takes an `exchange` MIC code. `'XNYS'` (NYSE) is only the default-arity value.
`tcal.exchanges` enumerates the full set (`XNAS` Nasdaq, `XLON` London, `XTKS`
Tokyo, …). An unknown code raises a clear `UnknownExchangeError`.

## Scalars vs table functions — THE core convention (read first)

The VGI SDK makes **scalar functions positional-only**: `name := value` named
args are rejected for scalars and only work on table functions. This drove the
whole function-shape split here:

- **Per-row functions are scalars with arity overloads** so they work inline in
  a projection (`SELECT is_trading_day(trade_date) FROM fills`):
  `is_trading_day(date)` / `(date, exchange)`; same shape for
  `next_trading_day`, `previous_trading_day`, `add_trading_days`,
  `trading_days_between`, `market_open`, `market_close`, `is_early_close`.
  Defaults are positional (`exchange` defaults to `'XNYS'`).
- **Set-returning functions are table functions** and DO use named args:
  `trading_sessions(start, end, exchange := ...)`,
  `trading_schedule(start, end, exchange := ...)`. `exchanges` is a scan-backed
  discovery **table** (no parentheses: `SELECT * FROM tcal.exchanges`).

If you're tempted to give a scalar an `exchange :=` arg, you can't — add an
overload instead. (This same constraint shapes every sibling worker.)

## Sharp edges (learned the hard way)

1. **Named-arg Arrow type must be pinned, or a NULL default breaks the wire.**
   A table-function named arg whose Python default is `None` infers Arrow type
   NULL, so a supplied value fails at cast time (`VARCHAR -> "NULL"`). Pin
   `arrow_type=pa.string()` on the descriptor. The in-process pytest harness did
   NOT catch this in the parent worker — only the real ATTACH+SELECT E2E did.
   **Run the SQL suite.**
2. **`haybarn-unittest` skips `require vgi`.** Under haybarn the extension is not
   autoloaded for `require`, so a `.test` using `require vgi` is silently
   SKIPPED. Use an explicit `statement ok` / `LOAD vgi;` instead (the SQL files
   here already do). `LOAD vgi` also works under the locally-built vgi unittest.
3. **DATE ↔ date32, TIMESTAMP ↔ timestamp(us).** Round-trip these correctly;
   `trading.py` keeps everything in `datetime.date`/`datetime` and the Arrow
   mapping is in the function wrappers.
4. **TIMESTAMPTZ scalars need an explicit `Returns(arrow_type=...)`.** A
   `pa.TimestampArray` return raises `TimestampArray requires explicit
   arrow_type in Returns()` at class definition unless you pass
   `Returns(arrow_type=pa.timestamp("us", tz="UTC"))` — see `market_open` /
   `market_close`. `exchange-calendars` returns UTC tz-aware instants; the
   worker maps them to DuckDB `TIMESTAMPTZ`. SQL assertions compare against
   `TIMESTAMPTZ '... +00'` literals so they're timezone-independent.
5. **`exchange-calendars` coverage window is bounded** (~20yr back to ~1yr
   ahead). `trading.py` is written bounds-safe via `searchsorted` on
   `cal.sessions`, so out-of-window dates return `None`/empty rather than
   raising. It also pulls in `pandas` + `numpy`; the calendar objects are
   `lru_cache`d per process (the state VGI's pooled worker amortizes).

## Testing

```sh
uv run pytest -q              # unit: pure math + Client RPC integration
make test-sql                 # E2E: haybarn-unittest over test/sql/*  (authoritative)
make test                     # both
uv run ruff check . && uv run mypy vgi_trading_calendar/
```

`make test-sql` sets `VGI_TRADING_CALENDAR_WORKER="uv run --python 3.13
trading_calendar_worker.py"`, puts `~/.local/bin` on PATH, and runs
`haybarn-unittest --test-dir . "test/sql/*"`. Install the runner once with
`uv tool install haybarn-unittest`. **The SQL suite is authoritative** — unit
tests call functions directly and can pass while the RPC path is broken. CI
(`.github/workflows/ci.yml`) runs unit + lint + vgi-lint + a gated `integration`
matrix (subprocess/http/unix transports) that runs `ci/run-integration.sh`.

## Conventions

- `exchange-calendars`: `exchange` is an ISO-10383 MIC code; unknown codes raise
  `UnknownExchangeError`, surfaced as a clear SQL error.
- A *session* is a trading day; `market_open` / `market_close` are UTC instants.
- Nothing is published or deployed yet; all functions are pure/offline (no model
  downloads, no network), so the suite is fast and hermetic.
