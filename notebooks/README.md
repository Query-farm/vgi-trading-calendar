# Cross-market UTC overlap notebook

[Cross-market UTC overlap](01_cross_market_utc_overlap.ipynb) retrieves NYSE and London session calendars, computes their shared regular-session intervals in SQL, and compares the weeks around their staggered autumn clock changes. Closed dates, unknown calendar coverage and exact-close membership receive separate treatment.

## Run from this directory

Install [uv](https://docs.astral.sh/uv/) and Git. The notebook uses Python 3.13 or 3.14 with locked Haybarn 2.0.0rc11; the worker explicitly uses Python 3.13. First use needs network access for dependencies, the published VGI extension and the pinned remote Git worker. Calendar calculations are then offline. This directory can be copied alone; no local worker source or build is required.

```bash
uv sync --frozen
uv run --frozen python execute.py
```

The visible literal launcher pins public Git revision `ac3c95091e2b248f995b24767021283cb46a1b9e`, VGI SDK 0.51.0 / RPC 0.53.1, exchange-calendars 4.13.2, pandas 3.1.1, NumPy 2.5.4 and tzdata 2026.6. These match the tested source dependency versions. The notebook environment remains separate from that worker runtime. Rerun default and experiment after changing a pin.

For interactive use, register this environment and select it in Jupyter:

```bash
uv run --frozen python -m ipykernel install --user --name vgi-trading-calendar-notebooks --display-name 'Python (trading-calendar notebooks)'
```

Restart and run all after changing the visible week parameter. Connection and analytical SQL remain visible; Python imports, plotting, interpretation source and cleanup are folded. The runner uses a temporary kernel with this directory as cwd and writes only successful outputs. Overrides need a separate output destination; unknown parameters and source-directory output destinations are rejected.

## Dates, time intervals and coverage

`WEEK_START` accepts exactly `2026-10-19` (default), `2026-10-26` or `2026-11-02`. Each selected window includes seven calendar dates. Both `XNYS` and `XLON` schedules are retrieved once for the fixed inclusive reference window **2026-10-19 through 2026-11-08**. A date spine and per-row worker flags preserve covered closed dates, rather than assuming every missing schedule row is a closure.

The source is the pinned library's calendar definitions, not an API feed, captured dataset or observed trading activity. [Provenance](fixtures/provenance.json) records the window and controls; the `fixtures/` directory contains this explanatory manifest, not fake calendar outputs. All calendar math runs through the real worker; Python formats results and charts.

`trading_schedule` has inclusive date endpoints. `trading_days_between` counts a half-open date range `[start,end)`. Open/close fields are timezone-aware instants; charts extract clock hours explicitly in UTC. Shared time is the positive intersection of **[open,close)** intervals. An event exactly at shared open is inside; one exactly at shared close is outside. The two event probes are explicitly invented boundary controls.

A covered closed date has zero overlap. Unknown calendar coverage stays NULL; the notebook requires complete coverage of its fixed comparison window. A Saturday and 1900-01-01 demonstrate that false and NULL are distinct even when both have no opening timestamp. The library's default coverage window moves with execution time, so pinning its package does not create an indefinitely frozen calendar export. If the selected dates later leave that window, the coverage assertion fails instead of silently shortening the analysis.

Both selected exchanges have continuous modeled regular sessions within these returned bounds. Other calendars can have intraday breaks that need additional interval handling; this worker's schedule schema exposes only open/close. The notebook does not model unexpected halts, extended hours, auctions beyond those bounds, execution liquidity or settlement rules.

## Focused experiment

```bash
uv run --frozen python execute.py --parameters '{"WEEK_START":"2026-10-26"}' --output-dir validation/later-week
```

Moving from October 19 to October 26 shifts the selected week while retaining the same full-period relation. Compare UTC session bars and total shared hours; local session lengths need not change when UTC offsets change. The fixed three-week chart and weekly summary should be identical across runs. Restore `2026-10-19` for the default.

Twelve SQL checks cover complete date spines, identities, calendar coverage, schedule/flag agreement, interval bounds, overlap limits, closed-date zeros, half-open date counts, boundary-event membership and aggregate reconciliation. Separate controls verify closed versus unknown flags. Saved successful outputs embed both charts; generated logs, chart PNGs and experiment copies are ignored under `validation/`. Experiment copies include branding, helpers, provenance and the locked environment. [STANDARD.md](STANDARD.md) records presentation conventions.

Source validation passed 44 pytest tests, 57 stdio SQL assertions, 59 HTTP assertions and 57 Unix assertions through the supported Haybarn unittest runner. Source Ruff/format, mypy and isolated pydoclint passed; metadata reports 100/100 L2 with zero findings. The source tests emit eight upstream pandas deprecation warnings. No engine rebuild, source change or root lock modification was needed.
