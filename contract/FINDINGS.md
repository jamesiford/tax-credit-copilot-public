# Findings: things that look wrong, recorded unchanged

The Python implementation is the oracle. None of these was fixed or smoothed; each is in the recordings exactly as observed. A port must
decide, per item, whether to reproduce it (parity) or fix it deliberately (a recorded deviation). `case` names the recorded exchange
(`<recording>:<step id>`).

## Defects (5xx, hangs)

| # | Finding | Evidence |
|---|---|---|
| F-1 | `GET /api/simulate/portfolio/{year}?magnitude=999999999` never returns: it is CPU-bound with no bound or timeout. The case is **omitted from the scenarios** (it would hang the recorder); the other out-of-range magnitudes (`abc`, `-1`, `0`) are recorded. | found while recording `p1_reads`; excluded in `scenarios/build.py` |
| F-2 | `GET /api/v2/portfolio?scope=all` answers a plain-text **500**. | `p1_query_edges:portfolio.scope` |
| F-3 | `GET /api/v2/clients/99999999999999999999/units` (an id beyond 64 bits) answers a plain-text **500** (integer overflow in the store binding); a smaller unknown id answers a normal not-found. | `p1_query_edges:unknown.client-huge` |
| F-4 | `GET /api/progress/{year}?within=-1` answers a plain-text **500**. | `p1_reads:get-api-progress-tax-year.query-within-negative` |
| F-5 | A second `POST /api/clients/{id}/packages` for the same client and year answers **500**: the blob path is derived from the run and the content hash and "blob paths are never reused". The second build of an identical package is an unhandled error, not an idempotent 200 or a 409. | `p1_artifacts_ai:package.create-again` |
| F-6 | `GET /api/workspace/assumptions` answers a plain-text **500** while every other sealed-workspace route answers **503** with a JSON reason when the reference inputs are absent. | `p1_reads:ok.api-workspace-assumptions` |

Every 500 body is `text/plain; charset=utf-8` with the exact bytes `Internal Server Error`; it is not the `{"detail": ...}` JSON the
handled errors use. A client that always parses JSON fails on these.

## Behaviour that is probably unintended but is the contract

| # | Finding | Evidence |
|---|---|---|
| F-8 | `POST /api/claims` with an identical body twice answers **201** twice and creates two rows (no 409, no idempotency). | `p1_writes:claims.create-duplicate` |
| F-9 | Money is a **string** in most bodies (`"identified_usd":"66500"`), and an input number is echoed as the text of the Decimal it became: `claimed_usd: 1234.5` -> `"1234.5"`, `1e3` -> `"1000.0"`, `"1234.50"` -> `"1234.50"` (scale preserved). A port needs decimal-with-scale semantics, not double. | `p1_writes:claims.create-money-*` |
| F-10 | `GET /api/rules` embeds **file modification times** (`last_update_iso`, per-rule `updated`). They are the clone time of whoever checked the repository out, so a recording only holds on one machine. The harness freezes `os.stat` for rule files (a stable per-path time); the product value is environment-dependent. | `p1_reads:ok.api-rules` |
| F-11 | `HEAD` on every `GET` route answers **405** (`Allow: GET`), and `OPTIONS` without an `Origin` answers 405 with body `{"detail":"Method Not Allowed"}`. | `p1_reads:head.health`, `options.health` |
| F-12 | A trailing slash answers **307** with an **absolute** `Location` built from the request's `Host` (`http://<host>/api/health`). The recorder rewrites the origin to `{origin}` (the only normalisation; `docs/normalisation.md`). | `p1_reads:trailing.health` |
| F-13 | CORS is `allow_origins=*`, methods `GET, POST, PUT, OPTIONS` only: a preflight for `DELETE` or `PATCH` is a **400** with a text body, and headers are reflected (`allow_headers=*`). `max-age` is 600. | `p1_reads:cors.preflight*`, `p1_auth:cors.*` |
| F-14 | Writer entitlement is not uniform. With `CHANNEL_ENFORCE_WRITER_FOR_USERS` on, a plain `TCC.User` (not a writer) is refused on claims, engagement, transition, base-year, drafts and findings (403 "this user is not entitled to make changes") but **may** `POST /api/claims/assess`, `POST /api/v2/clients/{id}/runs`, `POST /api/rules/{code}/verify` and start run batches. | `p1_auth:reader.*` |
| F-15 | An agent token reading `GET /api/v2/program-drafts` answers **403** "the command's author is not the user the agent acts for": a read is refused by a writer-style author check. | `p1_auth:agent.read-draft-list` |
| F-16 | The agent-forbidden-write refusal (403 "this route is not available to the channel agent") comes **after** the acting-user header is validated: the same forbidden route answers 400 without the header and 403 with it. | `p1_auth:agent.forbidden-checked-before-header` vs `agent.forbidden-assess` |
| F-17 | `GET /api/v2/portfolio?sort=bogus&order=sideways` and `status=bogus` are accepted (200) and echoed, not rejected: unknown enum values are silently ignored on some parameters and rejected (422) on others. | `p1_query_edges:portfolio.sort-bogus`, `portfolio.status-bogus` |
| F-18 | `GET /api/v2/clients/{id}/runs/latest` answers 404 "has not been calculated yet" even after a successful `POST /api/v2/clients/{id}/runs` in this (in-memory run-manifest) configuration, while the unit grid for the same client reports `calculation_state: calculated`. In the deployed (Warehouse) configuration this may differ; it is a hermetic-profile limit. | `p2_reads_writes:client2002.run-latest-after` |
| F-19 | The channel gateway answers **502** for an unusable download ticket (`invalid_arguments` code) where the API would answer 4xx. | `g1_rest:download.unknown-ticket` |
| F-20 | `GET /channel/v1/downloads/{ticket}` is single-use: the replay answers **410** `confirmation_replayed` (the error vocabulary of the confirmation service is reused for downloads). | `g1_rest:download.owner-again-single-use` |

## Environment findings

| # | Finding |
|---|---|
| E-1 | The only available interpreter (`.venv`) is **Python 3.14**, while the product targets 3.12. On 3.14 `sqlite3` no longer registers default `date`/`datetime` adapters, so the product's own SQLite stores fail to bind dates (a 500 on package creation). The harness registers the 3.12 adapters (`harness/freeze.py`). A .NET port is unaffected, but anyone re-recording on 3.14 without the harness gets different results. |
| E-2 | `backend/tests/data_engine_fixture.py` translates `SELECT TOP n` but not `SELECT DISTINCT TOP n`, which the unit drill issues; the fixture world therefore 500s on `GET /api/v2/clients/{id}/units/{unit}` until `harness/gold.py` adds the translation. Not a product defect. |
| E-3 | `RUN_WORKER_INLINE` defaults on for `ENVIRONMENT=local`; an API in that mode races a background worker against requests. The harness pins it off and exposes `POST /__contract__/drain`. |
| E-4 | A base-year save starts a daemon **recalculation thread** the response does not wait for; what the next read says depends on how fast it ran. The harness defers it until the response is sent and finishes it before the next request (`freeze._freeze_threads`, `control._gated`). A port must offer the same ordering for the replay to be repeatable. |
| E-5 | `RunClientCalculationCommand` writes claims as a side effect; `tests/data_engine_fixture.run_engine` therefore needs the operational claims repository passed in (the harness does) or the engine run's claim is lost. |
| E-6 | The `claim package` xlsx is not byte-reproducible by construction (a worksheet is spooled through a temp file whose mtime becomes the zip member time). Recordings compare zip **members** (name, size, SHA-256), never the container; `x-content-sha256` and the JSON `sha256` of a package are container hashes and will differ for a port. |
| E-7 | The governed data tools (`data_catalog`, `data_query`, `data_distinct_values`) answered 500 through the gateway in the first recording pass because the harness had not wired a data-query service; with the SQLite adapter wired (`harness/world.py`) they answer normally. A real deployment with the Warehouse unreachable was not exercised. |
