# Cross-market UTC overlap

[Shared market hours change when local clocks change](01_cross_market_utc_overlap.ipynb)
retrieves New York (`XNYS`) and London (`XLON`) session calendars, computes their
shared regular-session intervals in SQL, and compares three weeks around staggered
autumn clock changes. It distinguishes a supported exchange code, a covered open or
closed date, and an unknown date outside the calendar's coverage.

The worker supplies **calendar definitions, not live market data**. The example
measures modeled session overlap; it does not observe trades, liquidity, unexpected
halts, extended hours or settlement rules. Only the two exact-open/close event probes
are invented controls. [Provenance](fixtures/provenance.json) records the window and
assumptions; this directory contains no replay calendar outputs.

## Run from this directory or Colab

Install [uv](https://docs.astral.sh/uv/) and Git. Initial setup needs network access
for dependencies, the VGI extension and published worker. Calendar calculations are
then offline. The notebook runs without the worker checkout, including as a
notebook-only copy through its Colab badge.

```sh
uv sync --locked
uv run --locked vgi-notebooks 01_cross_market_utc_overlap.ipynb
```

Select `notebooks/.venv/bin/python` in an editor, use `notebooks/` as the working
directory, and restart/run all. The visible Colab bootstrap installs the shared
package's base dependencies; local publication adds `[runner]`. The locked notebook
environment uses shared **v0.3.19** and Haybarn **2.0.0rc11**. It starts SQL with a
fresh empty temporary secret directory and persistent secrets disabled.

The visible connection is a short release-tag launch:

```sql
ATTACH 'tcal' (TYPE vgi,
 LOCATION 'uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-trading-calendar@v0.5.0 vgi-trading-calendar-worker');
```

The release source is pinned to [v0.5.0](https://github.com/Query-farm/vgi-trading-calendar/releases/tag/v0.5.0)
(commit `524b7d47e5e606da3c4e56286717361eed0f2f29`). Its own declarations resolve
the worker libraries in an isolated environment; no `--with` overrides or calendar
libraries in the notebook kernel are needed. The tested versions are
exchange-calendars **4.13.3**, pandas **3.1.1**, NumPy **2.5.4**, tzdata **2026.6**,
VGI Python **0.51.1**, VGI RPC **0.53.1** and PyArrow **26.0.1**. These transitive
versions can change in a future fresh cache. Recheck the displayed dates, outputs
and provenance when upgrading or resolving a different environment.

## Dates, intervals and coverage

`WEEK_START` accepts exactly `2026-10-19` (default), `2026-10-26` (experiment), or
`2026-11-02`. Each selected window contains seven calendar dates. Both schedules are
retrieved once for **2026-10-19 through 2026-11-08 inclusive**. The discovery relation
must contain both exchange codes before retrieval; code support alone does not
establish date coverage. A complete date spine and per-row session flags retain
closed dates, rather than guessing that every absent schedule row means closure.

`trading_schedule` has inclusive date endpoints. `trading_days_between` counts a
half-open **date** range `[start,end)`. The notebook displays both corresponding
New York counts, using 9 November as the exclusive upper endpoint and 8 November as
the inclusive upper endpoint. This date count is distinct from shared hours.

Open/close fields are timezone-aware instants. Charts extract clock hours explicitly
in UTC, and shared time is the positive intersection of **[open,close)** intervals.
An event exactly at shared open is inside; one exactly at shared close is outside.
A covered closed date has zero overlap. Unknown coverage stays NULL, and the notebook
requires complete coverage of the fixed reference window. Scalar controls show actual
Monday opening/closing instants alongside a Saturday and 1900-01-01: the latter two
have no timestamps but different false/NULL session flags.

The library's default coverage window moves with execution time. Pinning its package
would not create an indefinitely frozen calendar export; if these dates later leave
that window, the coverage assertion fails rather than silently shortening the analysis.
Both selected exchanges have continuous modeled regular sessions within the returned
bounds. Other calendars can have intraday breaks; this worker's schedule exposes only
open/close and would require additional interval handling for those calendars.

## Focused experiment

Predict how London's UTC bars move relative to New York, then change only the week:

```sh
uv run --locked vgi-notebooks 01_cross_market_utc_overlap.ipynb \
  --parameters '{"WEEK_START":"2026-10-26"}' \
  --output-dir validation/later-week
```

Compare the selected interval plot and shared hours. The full 21-date relation,
three-week chart, weekly summary, exchange discovery and date-count table stay fixed.
The default has 10 shared hours and the later week 15, with five joint sessions in
each week. The individual modeled session durations remain 6.5 hours in New York
and 8.5 hours in London. Restore `2026-10-19` for the saved default.

The runner preserves the last successful notebook, rejects unknown parameters, and
requires a separate destination for overrides. Published plots use linked SVGs under
`charts/`; ignored PNG previews/logs are under `artifacts/` and `validation/`.

## Coverage and verification

[coverage.json](coverage.json) maps **six of eleven** released and current public
names to meaningful visible SQL, executed results and interpretation. Complete native
function/table/view exports are in [coverage/](coverage/), including empty view exports.
The denominator includes all named objects, with overloads counted once. The five
uncovered names are `add_trading_days`, `next_trading_day`, `previous_trading_day`,
`trading_sessions` and `is_early_close`; this focused overlap story does not add
unrelated navigation or settlement examples merely to mention them.

The released and current-main (`e69ece1ac91d73e18737dc8544f4c7ddf80f07e3`) catalogs
were collected through actual Haybarn attachments to public Git revisions. Current
source adds composed metadata examples; calendar computations are unchanged from the
release. The notebook's hash-bound success receipt is for the released worker.
Reviewed current-interface coverage is distinguished from exact-current notebook
execution, which is not claimed.

Validation covers the default, a detached notebook-only later-week experiment with a
cold worker cache, twelve SQL invariants, open/closed/uncovered controls, scalar versus
schedule timestamp agreement, three runner guards and two invalid-parameter guards.
A fresh Python 3.12 kernel preloaded with older pandas/Matplotlib/IPython/ipykernel/
jupyter-client runs the full base-only bootstrap without upgrading those loaded
packages or installing the worker calendar libraries. Hosted Colab was not manually
run; this is automated compatibility verification.

For this notebook-only revision, existing green [source CI at the public baseline](https://github.com/Query-farm/vgi-trading-calendar/actions/runs/43584610155)
is reused. No worker rebuild, source test repetition or root lock change was needed.
The original checkout and its untracked notebook work are preserved separately.
