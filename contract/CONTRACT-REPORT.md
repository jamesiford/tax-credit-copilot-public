# Contract report

The Python API is the oracle. This report says what was recorded, how repeatable it is, what is odd about it, and what the .NET 10
host has to do to match it. Numbers are from the final runs on branch `contract/capture` (nothing outside `contract/` was changed or pushed).

## 1. What was captured

| Surface | Count |
|---|---|
| API operations (method + path) | **93** (91 paths; plus FastAPI's `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`). The brief said 88; 18 of the 93 declare a real pydantic `response_model`, **75 are untyped** (`-> dict`) |
| Channel gateway | 9 routes (`/channel/health|ready`, `/channel/v1/tools`, `/channel/v1/tools/{tool}`, narration audit, downloads, `/mcp` POST/GET/DELETE), **36 tools** in `tools/list` (37 with `CHANNEL_DEBUG_WHOAMI`), every input schema and description byte-for-byte in `inventory/channel.json` |
| Orchestrator | 25 tools offered to a model, the planner/narrator prompt texts (hashed, in full), 39 deterministic turns recorded; model behaviour specified by 313 existing pytest functions (`docs/ORCHESTRATOR-SPEC.md`) |
| Agents | 12 prompt files + `manifest.json` hashes, the `publish_agent` request for each agent captured with a fake Foundry client (`recordings/agents.json`) |
| Environment | 139 variables found by an AST scan; **0** read by code but missing from `ENV-VARS.md`; 123 documented tokens not found by the static scan (the scan sees neither tests, scripts nor infra) |
| Data | SHA-256 of both DDL files and of the 6 migrations; 24 tables; 38 rule-pack files hashed |
| Recordings | **12 scenarios, 1,765 HTTP exchanges + 4 control steps, 3.8 MB** (JSON Lines, no compression needed); seed 6.1 MB gzip |
| Status codes seen | 200 570 · 201 15 · 202 15 · 307 61 · 400 32 · 401 28 · 403 43 · 404 127 · 405 246 · 409 32 · 410 1 · 413 1 · 422 547 · 429 5 · 500 8 · 502 2 · 503 32 |

Scenarios: `p1_reads` (584: every GET route, plus the generated battery for each), `p1_query_edges` (71), `p1_writes` (366: every write route with a valid body and the generated invalid-body battery), `p1_program_drafts` (175: the full draft lifecycle to an exported bundle), `p1_artifacts_ai` (36: packages, downloads, capabilities, chat and page-summary streams), `p1_workspace_unavailable` (30), `p1_auth` (114), `p2_reads_writes` (74), `p2_run_batches` (62: dry run, create, idempotency replay, drain, skip-unchanged, cancel, retry), `g1_rest` (142), `g1_mcp` (103), `g1_ratelimit` (10).

## 2. Coverage

`COVERAGE.md` is the route-by-case matrix (generated). Summary:

* Every one of the 93 operations has at least one recording; **82 have a success (2xx)**, 11 do not, each with a reason: the 10 sealed `/api/workspace/*` routes (they need the private reference extract `One.csv..Four.csv`, gitignored and absent), `POST /api/rules/ingested/{state}/apply` (needs the live rules-ingestion service) and `GET /api/v2/clients/{id}/runs/latest` (404 "has not been calculated yet" even after a run in the in-memory run-manifest configuration: FINDINGS F-18). Their error answers are recorded.
* Every tool in `tools/list` has a typical and an invalid call through REST **and** through MCP.
* Not exercisable hermetically, by design: a real model (`/api/chat`, `/api/summary` use the scripted fallback and their event framing is recorded), live web retrieval, the sealed workspace's success bodies. A 413 exists only on the gateway.
* Cases deliberately **not** recorded: `magnitude=999999999` on the portfolio simulation never returns (F-1); header values an HTTP client cannot send (`Bearer ` with a trailing space and a blank acting-user header were dropped from `p1_auth`, as `h11` refuses them on the wire).
* No unexplained gaps (the matrix lists the reason for every class of empty cell).

## 3. Determinism evidence (gates G2/G3)

* Every scenario runs in its own fresh process. `capture --check` re-records into a temp directory and compares bytes: **identical on every run, twice in a row, three-wide** (the final pair covers all 12 recordings).
* **The oracle is Python 3.12**, the version the product runs on, and that is enforced in code: `CONTRACT_PYTHON` defaults to the 3.12 environment (`contract/oracle.py`), and `capture`, `replay`, `selftest`, `seed_export`, `orchestrator_capture` and the harness processes refuse to start on any other minor version unless `--allow-other-python` is passed (cross-check only; the output is stamped with the interpreter and zlib build). The first recordings were made on 3.14.2; re-running on 3.12.13 showed the HTTP behaviour identical (1,755 / 1,769 exchanges) and 14 differences, all the **size and SHA-256 of a zip/xlsx container**. Cause (measured): the 3.14.2 Windows build links zlib-ng 2.2.4, 3.12.13 links zlib 1.3.2; the same input at the same level deflates to different bytes. The members (name, size, member SHA-256) were identical in every case.
* Honest history: the first `--check` runs failed, and each failure was a real source of volatility that was then **frozen at its source** rather than normalised: xlsx zip timestamps (package hash differed every run), rule-file mtimes (clone time leaking through `/api/rules`), `git rev-parse` in `code_commit`, a background base-year recalculation thread whose uuid and clock draws raced the next request (visible only under CPU load), and the in-process transport vs a real socket (`Location` host). Full list with symptoms: `docs/normalisation.md`.
* **Two normalisation rules exist**: the `Location` header's origin -> `{origin}`, and the size and SHA-256 of a zip/xlsx container at 7 listed routes (12 field locations, plus the recorded `length`/`sha256` of the three responses that are the container) -> `{container.size_bytes}` / `{container.sha256}`, applied at record **and** replay time, only when the value has the right shape (and, for a header, matches the body it came with). Zip **members are always compared**, one diff per member. The container's own bytes never are: that is tier D below. The 8 recorded exchanges that changed on re-recording are exactly the container fields.
* Seed: each profile built twice gives identical `manifest.json` (every row count and file hash); P1 18,111 rows / 11 tables, P2 390,660 rows / 20 tables; the API's per-client `employees_evaluated`, `scope` and `portfolio` totals agree with the seed rows. The seed files are gzip, whose bytes also depend on the zlib build: the decompressed content of all 31 tables is identical on 3.12 and 3.14 (13 `.gz` files differ in bytes only), and the manifest now carries `content_sha256` (decompressed) next to `sha256` (the file as shipped).
* **G4**: replay in strict mode against a **real `uvicorn` on a free port in a separate process**: **1,769 / 1,769 identical on 3.12** (the oracle); against the in-process harness: **1,769 / 1,769**. **Cross-check on 3.14.2** against the 3.12-recorded files (`capture --check` and strict replay, both with `--allow-other-python`): **1,769 / 1,769** and 12/12 recordings byte-identical. Reports: `docs/replay-spawn-312.*`, `docs/replay-inprocess-312.*`, `docs/replay-spawn-314-crosscheck.*`.
* **Mutation self-test**: 72/72 caught on 3.12 and on 3.14. The original 10 perturbations of a recording (status, number text, number value, key order, header, missing field, extra field, changed error message, array length, null for a value) x 2 modes = 20, each naming route, case, category and field. Plus 26 mutations of **what the server answered**, before normalisation, x 2 modes = 52: a container size as a string / negative / a float, a hash `null` / a number / `true` / 63 characters / uppercase / absent / malformed (also the hash displayed in the gateway table), a header hash that is not the hash of the body, a zip member renamed / content changed / size changed / missing / extra / reordered, a response that is no longer a zip, a neighbouring field changed; and three control cases in which only the container's own bytes differ, which must (and do) report nothing (`docs/mutation-selftest.json`). In `semantic` mode the number-lexeme and key-order mutations are reported as *tolerated*, every other one still fails.

## 4. Catalogue of contract quirks

**Error shapes** (these differ by route family; a port must not unify them):

| Shape | Where |
|---|---|
| `{"detail": "<string>"}` | most handled errors: 404 unknown id, 409, 403 (client, writer, agent-forbidden), 401 (`no bearer token`, `invalid token: <PyJWT class>`), 400 acting-user, 405 `Method Not Allowed`, 404 `Not Found` |
| `{"detail": {"code", "reason", "remedy"?}}` | program drafts (`draft_conflict`, `invalid_transition`, `review_refused`, `preview_refused`, `local_write_refused`), rate limit 429 (`rate_limited`) |
| `{"detail": {"detail": "...", "code": "empty_selection"...}}` | run batches (a `detail` inside `detail`) |
| FastAPI validation: `{"detail": [{"type", "loc", "msg", "input", "ctx"?}]}` | every 422 from binding: `loc` is `["body", ...]`, `["query", name]`, `["path", name]`; `type` is pydantic v2's (`int_parsing`, `missing`, `string_too_long`, `literal_error`, `json_invalid` with `loc: ["body", <char offset>]` and an `ctx.error` from Python's JSON parser, `model_attributes_type`) |
| `DependencyUnavailable` 503: `{"dependency", "reason", "remedy"...}` (top level, no `detail`) | unconfigured source |
| `{"error": {"code","message","retryable",...}, "correlation_id"}` | the channel gateway, always |
| `text/plain` `Internal Server Error` | every unhandled exception (8 recorded; F-2..F-6) |

**Numbers and money.** Money is a JSON **string** with the Decimal's scale (`"66500"`, `"1234.5"`, `"1000.0"`); an input number is echoed as the text of the Decimal it became (F-9). Counts and years are integers; headcounts/hours are floats written by Python's `repr` (`17.25`, `65.38`, `1.0`, `0.0`, `1e-05` forms occur): a port must reproduce shortest round-trip floats, and `5.0` must not become `5`. Some totals are integers where the same field elsewhere is a float (`estimated_credit_total_usd: 306670`).

**Key order.** Insertion order, which is the construction order in Python, **not** alphabetical (`near_total_unfiltered`..`employees` appear in handler order) and not the schema's. Recorded, and compared in strict mode.

**null vs absent.** Present-with-null is the norm (`"entity_id": null`, `"message": null`); optional blocks are sometimes absent. Compared by presence.

**Dates.** Mixed within one document: `2026-01-15` (date), `"2026-01-15 12:00:00"` (SQL text, no `T`, no zone), `"2026-01-15T12:00:00+00:00"` (offset), `"2026-01-15T12:00:00Z"` (`run_started_at`), minute-precision offsets (`"2026-11-15T01:08+00:00"`). Per field, not per type.

**Headers.** JSON responses carry only `content-type: application/json` (no charset) and `vary: Origin` when CORS applies. Plain-text responses carry `text/plain; charset=utf-8`. 405 carries `allow`. 429 carries `retry-after`. 401 carries `www-authenticate: Bearer`. Downloads carry `content-disposition: attachment; filename="..."`, `cache-control: no-store`, `x-content-sha256`; draft export carries `x-bundle-sha256`. SSE carries `cache-control: no-cache`, `x-accel-buffering: no`.

**Event streams.** `/api/chat` and `/api/summary` return `text/event-stream`; frames are `event: <name>\ndata: <json>\n\n`; chat: `status`, `agent_start`, many `token`, ..., `done`; summary: `brief`, `fallback` or `token`, `check`, `done`, or `error` then `done`. Recorded as ordered events (`events[i].event/data`).

**Downloads.** xlsx package and draft bundle zip are compared by members (name, size, SHA-256) because the container bytes are not portable (E-6).

**Routing.** FastAPI semantics: `HEAD` -> 405; `OPTIONS` -> 405 unless CORS preflight; trailing slash -> 307 with absolute `Location`; unknown path -> `{"detail":"Not Found"}`; a wrong method -> 405 + `Allow`. Path params typed `int` reject non-integers with 422 (`int_parsing`) **before** any handler (the guard ignores a non-numeric id, so `abc` as a client id is 422, not 403, by the guard's code; not separately recorded under Entra). Query params: unknown names are ignored; repeated scalar parameters take the last value; empty `limit=` is 422; `limit=0` and `limit=-5` are 422 where `ge=1` is declared, while out-of-range values on routes without a bound are accepted.

## 5. What a default ASP.NET Core host would get wrong

1. **Property order, naming, nulls.** `System.Text.Json` preserves declaration order for POCOs, but Python's order is construction order of dicts: typed records will not match for the 75 untyped routes. Use ordered `JsonObject`/`JsonNode` or source-generated converters; set snake_case; do **not** drop nulls (`DefaultIgnoreCondition.Never`).
2. **Numbers.** `double 5.0` serialises as `5`, Python emits `5.0`; `decimal` serialises `1000.0` as `1000.0` only with scale preserved; money must be a string with scale; very large integers. Provide custom converters per field family and compare the recorded number text.
3. **Escaping.** STJ escapes non-ASCII and `< > & ' +` by default; Python's `JSONResponse` writes UTF-8 literally with compact separators. Use `JavaScriptEncoder.UnsafeRelaxedJsonEscaping` (or a custom encoder) and compact output. Raw-byte equality is then achievable.
4. **Validation errors.** `[ApiController]` returns `application/problem+json` (`type/title/status/errors`) with 400; the contract is 422 and pydantic's `{"detail":[{"type","loc","msg","input","ctx"}]}` including pydantic's English messages and `type` codes. The JSON-body-syntax error even reports a character offset from Python's parser (`loc: ["body", 1]`).
5. **Model-binding strictness.** FastAPI/pydantic reject `"1.5"` for an int, accept numeric strings for money, treat an empty body as "Field required", a JSON array/`null`/string as `model_attributes_type`, and ignore unknown body fields (no `additionalProperties` error); ASP.NET binds leniently (coerces, defaults to 0) or fails differently. Repeated query keys and `limit=` (empty) differ.
6. **ProblemDetails vs `{"detail": ...}`** for 401/403/404/405/409/429: all are plain `detail` bodies; ASP.NET's status-code pages and `UseExceptionHandler` produce different bodies, and unhandled exceptions must produce the bare text `Internal Server Error` (or be fixed deliberately, F-2..F-6).
7. **Trailing slash, HEAD, OPTIONS.** ASP.NET answers 404 for `/x/`, auto-serves `HEAD` for `MapGet` (200), and its CORS middleware answers 204 preflights; the contract is 307 with an absolute `Location`, 405, and 200 text/plain `OK` with `access-control-max-age: 600` and reflected request headers (`allow-headers: *` means "reflect"), 400 for a disallowed method.
8. **Header casing/`Vary`.** Recordings use lower-case names; HTTP/1.1 is case-insensitive but `vary: Origin` appears on every response when `Origin` varies; `content-type` has no charset for JSON.
9. **Culture and time.** Format with the invariant culture; reproduce the mixed date forms per field (section 4); a frozen clock is needed to replay (the hook contract in `README.md`).
10. **Auth semantics.** JWT validation order and messages (`invalid token: ExpiredSignatureError` etc. are PyJWT class names; the port must decide whether to reproduce the *text*), the `WWW-Authenticate: Bearer` rule, the app-only vs delegated token shapes, and the acting-user header parser (all in `docs/AUTH-CONTRACT.md`). Messages that name a Python exception class are the least portable part of the contract.
11. **Streaming.** Response buffering must be off (`X-Accel-Buffering: no`, `Cache-Control: no-cache`); the event names and framing above.
12. **Background work ordering.** After a base-year save the next read must see the recalculation finished (E-4), or the port must offer the `drain` hook.

## 6. A definition of "parity" for shadow comparison

| Tier | Must match | Who decides a deviation |
|---|---|---|
| **A: byte-identical after the two normalisations** (redirect origin; container size/hash, with every zip member still compared) | status code, `content-type`, `allow`, `retry-after`, `www-authenticate`, `location` path, `content-disposition`, all `x-*`, the decoded JSON value **including key order and number text** for every route in the *certified-figure path* (portfolio, units, unit drill, eligibility, onezero, claims, forecast, packages: anything a filed return depends on, except the tier-D container fields below) and for all gateway tool results | nobody: a deviation is a bug in the port |
| **B: semantic equality** (values equal; number lexeme, key order, raw bytes may differ) | everything else with a JSON body: drafts, run batches, ingestion, QC, designations, scope, rules | the platform owner, per route, recorded in a deviations file; lexeme and order differences must be *knowing* (the replay's `semantic` mode lists them) |
| **C: shape-equivalent** | error *shape family* and status for 4xx/5xx; the **message text** of errors that embed a Python exception class or a pydantic English message (`invalid token: ExpiredSignatureError`, `JSON decode error`) | the platform owner; clients that parse these strings must be found first |
| **D: out of scope** | **the bytes of a zip/xlsx container, and every value that is a function of them**: the `size_bytes` and `sha256` of a claim package (`POST /api/clients/{id}/packages`; `facts.result.size_bytes`/`sha256` of `claim_package_create_commit`; `facts.size_bytes`/`sha256` and the hash displayed in `blocks[1].rows[1][1]` of `claim_package_link`), the header `x-content-sha256` of `GET /api/clients/{id}/artifacts/{id}` and `GET /channel/v1/downloads/{ticket}`, the header `x-bundle-sha256` of `POST /api/v2/program-drafts/{id}/export`, and `bundle_sha256` / `bundle_bytes` of its `/export/manifest`; also timing, the 500 text if the defect is fixed (F-2..F-6), model output | recorded as deliberate deviations |

Why exactly these are tier D: a deflate stream's bytes depend on the zlib build (measured: 3.12.13 / zlib 1.3.2 and 3.14.2 / zlib-ng 2.2.4 differ on identical input) and a .NET host will always write different bytes again, so no host can be expected to match them. They are **not a hole**: for each of them the replay checks the value's shape (a non-negative integer; 64 lowercase hex), that a header hash is the hash of the body it came with, and **every member of the zip** (name, uncompressed size, SHA-256, order), which are tier A. A hash or size anywhere else (`trail_sha256`, `content_sha256`, the per-file `files[].sha256` of the export manifest) is not tier D. The seed `.gz` files are the same case: compare `content_sha256`, not `sha256`.

Run strict replay as the gate for tier A and semantic replay for the rest; every tolerated item must be listed and approved.

## 7. What the .NET host will need to reuse

* `contract/replay.py` (any HTTP server), `scenarios/*.json`, `recordings/*.jsonl`, `seed/` (load into SQL Server with `docs/data/schema/tcc-schema.sqlserver.sql`), the hook contract (`drain`, `env`, `mint`, optional `reset`) in `README.md`, the clock/id/secret freezing rules in `docs/normalisation.md`, `inventory/channel.json` (the 36 tool schemas and descriptions, byte for byte) and `agents.json`/prompt hashes.
* The `jsontext.py` idea: keep the number text and key order.

## 8. Open questions

1. Is 422-with-pydantic-shape a requirement of the **clients** (the React app, the gateway, the orchestrator) or an accident? Which of them parse `detail[].loc` / `type`?
2. Should the port reproduce the 8 recorded 500s (F-2..F-6) or fix them first? (The recordings keep them.)
3. Several routes are **not** writer-gated although they write (F-14). Port as-is or tighten?
4. `GET /api/v2/clients/{id}/runs/latest` 404s after a run in the in-memory manifest configuration (F-18). Is that the deployed behaviour too? It needs the Warehouse profile to settle.
5. The sealed workspace (`/api/workspace/*`) has no hermetic success path: where should its seed come from (the private reference extract cannot enter the repository)?
6. ~~Python 3.14 vs the product's 3.12 (E-1): which interpreter is authoritative for re-recording?~~ **Resolved: 3.12 is the oracle**, enforced in code (`contract/oracle.py`; the tools refuse other interpreters without `--allow-other-python`), the recordings were re-made on 3.12.13, and the 3.14.2 cross-check against them passes 1,769 / 1,769 (E-1, E-6).
7. Money columns are stored as floats in the SQLite harness; the Warehouse stores `DECIMAL(18,2)`. The recordings show strings with scale; confirm the deployed values have the same scale.

## 9. What I would do next

1. Add a **P3 profile on SQL Server** (a local container with the DDL and the seed) to settle F-18 and the decimal scale question.
2. Record the sealed workspace against a *synthetic* One..Four extract.
3. Turn `replay.py --mode semantic` into a CI job against the .NET host, with a deviations file.
4. Record error shapes under HTTP/1.1 keep-alive and chunking, and large-body caps (the API has none).
