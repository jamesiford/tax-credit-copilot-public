# Normalisation

The default is **no normalisation**. Volatility is removed by freezing its source in the harness (`harness/freeze.py`, `harness/hermetic.py`),
never by rewriting output. One output rule exists.

## The one normalisation rule

| Field | Placeholder | Proof it is volatile | Why it could not be frozen |
|---|---|---|---|
| response header `location` **origin** (`http://host:port`) | `{origin}` | The first replay of all recordings against a real `uvicorn` on a free port failed 60 of 1,400 exchanges, all `headers.location`: expected `http://contract.local/api/health`, actual `http://127.0.0.1:59104/api/health`. | The framework builds the redirect from the request's `Host`; the host is the caller's. The path part is still compared. |

Implemented in `contract/normalise.py: apply`. A record that was normalised carries `"normalised": [...]`, and the replay then does not compare the raw-byte hash of that response.

## Sources frozen instead (each was observed to differ between two identical runs before it was frozen)

| Source | Symptom before freezing | Freeze |
|---|---|---|
| Clock (`datetime.now/utcnow/today`, `time.time`) | `as_of`, `produced_at`, `created_at`, token expiry | one constant instant, 2026-01-15T12:00:00Z (a ticking clock would make a response depend on how often the product asked) |
| UUIDs (`uuid4/uuid1`) | claim, run, batch, draft, artifact, confirmation ids | a sequential counter, reset per process |
| `secrets.token_*` | confirmation and download tokens | the same counter family |
| `random` | seeded | `random.seed(20260115)` |
| `time.perf_counter` | durations in manifests/metrics | 1 ms per call counter |
| `git rev-parse HEAD` | `code_commit` changed with every commit to the worktree | `subprocess.check_output` answers a fixed value; `GIT_COMMIT` pinned |
| Rule-file mtimes | `/api/rules` `last_update_iso` was the clone time (`2026-11-15T01:08`) | `os.stat` of `backend/rules/**/*.json` returns a per-path time |
| Zip member timestamps (xlsx claim package) | package `sha256` differed on every run | `ZipInfo.from_file` returns the frozen time |
| Background recalculation thread (`rebase-recalc-*`) | uuid draws interleaved with the next request; run ids shifted by 1-4 under CPU load (`p1_writes` failed `--check` only when run 3-wide) | deferred until the response is sent and completed before the next request is accepted |
| Background start-up checks | `/api/ready` reported `running` for `stores` / `source_schema` | the harness waits for both to settle before the first request |
| Inline run worker | batch status raced the worker | `RUN_WORKER_INLINE=0` and an explicit `POST /__contract__/drain` |
| Per-caller rate limiter | `Retry-After` depended on real elapsed time | the limiter's clock is a constant |
| Minted tokens | a fresh RSA key per process | tokens are minted on request; recordings hold the placeholder `Bearer {{token.<name>}}` and never a token |
| Ports, hosts, temp dirs, `ARTIFACT_LOCAL_ROOT`, `OPERATIONAL_DB` | | temp directory per process; no path appears in a response |

## Proof of determinism

* `capture record` then `capture --check` twice, three-wide, all 12 recordings byte-identical each time (`docs/capture-log.md`).
* Replay against a real `uvicorn` (a separate process) and against the in-process harness: 0 differences in strict mode.
