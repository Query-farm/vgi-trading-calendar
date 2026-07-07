# CI: the vgi-trading-calendar worker integration suite

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the unit tests
and this repo's sqllogictest suite (`test/sql/*.test`) against the vgi-trading-calendar
VGI worker through the **real DuckDB `vgi` extension** on every push / PR.

## How it works (no C++ build)

Rather than building the vgi DuckDB extension from source, CI drives a
**prebuilt** standalone `haybarn-unittest` (the DuckDB/Haybarn sqllogictest
runner, published in Haybarn's releases) and installs the **signed** `vgi`
extension from the Haybarn community channel:

1. **Install the worker** — `uv sync --frozen` into a venv. `trading_calendar_worker.py`
   is a self-contained PEP 723 stdio worker the extension can spawn via
   `uv run trading_calendar_worker.py`.
2. **Download the runner** — the matching `haybarn_unittest-*` asset per
   platform from the latest Haybarn release.
3. **Preprocess** — the standalone runner links none of the extensions the
   tests gate on, so [`preprocess-require.awk`](preprocess-require.awk) rewrites
   each `require <ext>` into an explicit signed `INSTALL <ext> FROM
   {community,core}; LOAD <ext>;`. These tests skip `require vgi` (haybarn
   silently SKIPs it) and `LOAD vgi;` directly, so the awk also injects an
   `INSTALL vgi FROM community;` right before each bare `LOAD vgi;`. `require-env`
   and everything else pass through untouched.
4. **Run** — [`run-integration.sh`](run-integration.sh) stages the preprocessed
   tree, resolves `VGI_TRADING_CALENDAR_WORKER` (the ATTACH `LOCATION`) per the
   `$TRANSPORT` it's run with (see below), warms the extension cache once, then
   runs the suite in a single `haybarn-unittest` invocation. Any failed
   assertion exits non-zero and fails the job.

## Transport matrix (subprocess | http | unix)

The same `test/sql/*.test` suite is run over all three VGI transports — the
extension picks the transport from the `LOCATION` string the `.test` files
`ATTACH`, and `run-integration.sh` builds that string from `$TRANSPORT`:

| `TRANSPORT`  | `VGI_TRADING_CALENDAR_WORKER` (LOCATION)     | How the worker is reached |
|--------------|--------------------------------------|---------------------------|
| `subprocess` | `uv run … trading_calendar_worker.py`        | extension spawns the worker per query; Arrow IPC over stdin/stdout (default) |
| `http`       | `http://127.0.0.1:<port>`            | harness boots `trading_calendar_worker.py --http --port 0 --port-file <f>`, waits for the port-file, then ATTACHes that URL |
| `unix`       | `unix:///tmp/tcal-<pid>.sock`         | harness boots `trading_calendar_worker.py --unix <sock>`, waits for the socket to appear, then ATTACHes it |

The CI `integration` job is a `transport: [subprocess, http, unix]` × `os`
matrix; each leg runs `ci/run-integration.sh` with `TRANSPORT=<t>`. Run a single
transport locally with e.g. `TRANSPORT=http ci/run-integration.sh`.

### Port / readiness discovery

- **http**: the worker writes its auto-selected port to `--port-file`
  atomically (tmp + rename), so the harness watches for that file to appear and
  reads the port from it — it does **not** parse stdout. Boot line:
  `trading_calendar_worker.py --http --port 0 --port-file <f>`.
- **unix**: the worker prints `UNIX:<abs-path>` once bound; the harness polls
  for the socket file (`test -S`) to appear. Boot line:
  `trading_calendar_worker.py --unix <sock>`.

Both server processes are trap-killed on exit.

### HTTP transport needs the `httpfs` extension (resolved, not gated)

The vgi extension implements HTTP transport on top of DuckDB's **httpfs**
extension, so an `http://` ATTACH binds with

> `Binder Error: VGI HTTP transport requires the httpfs extension. Install it with: INSTALL httpfs; LOAD httpfs;`

unless httpfs is loaded first. This is a **dependency**, not a protocol
limitation, so we resolve it rather than gate: the http leg of
`run-integration.sh` injects a signed `INSTALL httpfs FROM core; LOAD httpfs;`
into each staged `.test` (right after the awk-injected `LOAD vgi;`). The
`.test` files themselves stay transport-agnostic.

> **Sharp edge — the runner silently SKIPs HTTP errors.** The haybarn/DuckDB
> sqllogictest runner's default skip list (`test_config.cpp`
> `ErrorMessagesToBeSkipped`) skips any statement whose error message contains
> `"HTTP"` or `"Unable to connect"`. Without the httpfs load, *every* HTTP-leg
> test SKIPs (the httpfs binder error contains "HTTP") and the suite reports
> "All tests were skipped" — a green-looking **fake pass**, not a real one.
> Always confirm the http leg reports `All tests passed (N assertions …)` with
> N > 0, not "tests were skipped". (To surface a masked HTTP error while
> debugging, add `set ignore_error_messages __none__` to a probe `.test` so the
> real message FAILs instead of skipping.)

### Per-transport status

- **subprocess**: GREEN. The default; the extension spawns the worker per query.
- **http**: GREEN (the base assertions + the injected httpfs INSTALL/LOAD
  statements). Requires the `httpfs` load above and the worker's `http` extra
  (waitress) — `pyproject.toml` ships an `http` extra (`vgi-python[http]`),
  the PEP 723 header lists `vgi-python[http]`, and CI runs
  `uv sync --frozen --extra http`.
- **unix**: GREEN. No extra deps; `--unix` is built into the worker's
  `Worker.main()`.

The suite here is entirely stateless scalar/table calls, so none of the known
inherent HTTP limitations (inline log streaming, partition-local state, input
buffering, strict order preservation) apply — nothing needed gating.

## Run it locally

```bash
uv sync --python 3.13 --extra http          # install the worker + deps (http extra for the http leg)
# point HAYBARN_UNITTEST at a haybarn-unittest binary (or a local DuckDB
# `unittest` built with the vgi extension). WORKER_CMD is the stdio command that
# runs the worker; the harness uses it directly for subprocess and boots it with
# --http / --unix for the other transports.
HAYBARN_UNITTEST=/path/to/haybarn-unittest \
WORKER_CMD="uv run --python 3.13 trading_calendar_worker.py" \
  TRANSPORT=subprocess ci/run-integration.sh    # or TRANSPORT=http / TRANSPORT=unix
```

`TRANSPORT` defaults to `subprocess`, and `WORKER_CMD` defaults to
`uv run --python 3.13 <repo>/trading_calendar_worker.py`, so a bare
`HAYBARN_UNITTEST=… ci/run-integration.sh` runs the subprocess leg.

Or use the Makefile target `make test-sql`, which installs `haybarn-unittest`
as a uv tool and points the worker at `uv run --python 3.13 trading_calendar_worker.py`.
