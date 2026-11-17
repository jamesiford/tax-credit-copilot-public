# Normalisation

The default is **no normalisation**. Volatility is removed by freezing its source in the harness (`harness/freeze.py`, `harness/hermetic.py`),
never by rewriting output. Two output rules exist, and the interpreter is pinned (`oracle.py`: Python 3.12, enforced in code) so that
neither has to absorb interpreter differences beyond the one documented in rule 2.

## The two normalisation rules

| # | Field | Placeholder | Proof it is volatile | Why it could not be frozen |
|---|---|---|---|---|
| 1 | response header `location` **origin** (`http://host:port`) | `{origin}` | The first replay of all recordings against a real `uvicorn` on a free port failed 60 of 1,400 exchanges, all `headers.location`: expected `http://contract.local/api/health`, actual `http://127.0.0.1:59104/api/health`. | The framework builds the redirect from the request's `Host`; the host is the caller's. The path part is still compared. |
| 2 | the **size and SHA-256 of a zip/xlsx container**, at the route/field pairs below only | `{container.size_bytes}`, `{container.sha256}` | The recordings made on CPython 3.14.2 were replayed against 3.12.13 (strict, real `uvicorn`): 1,755 / 1,769 identical, and all 14 failures were exactly these fields (table below). The members were identical: every zip-entry comparison passed. | The bytes of a deflate stream depend on the zlib build, which the product does not control: 3.12.13 here ships zlib 1.3.2, the 3.14.2 Windows build ships zlib-ng 2.2.4 (compat 1.3.1). Same input and level, different output, measured: the same 40 KB buffer deflates to 1,169 bytes with SHA-256 `5b882ebf...` on 3.14.2 and `a75ff0ec...` on 3.12.13. A .NET host (`System.IO.Compression`) will always write different bytes again. Freezing member timestamps (already done) makes the output repeatable on one interpreter, not equal across them. |

Both are implemented in `contract/normalise.py: apply` and applied **at record time and at replay time**, to what the server answered. A record that
was normalised carries `"normalised": [...]` listing what was rewritten, and the replay then does not compare the raw-byte hash of that response.

### Rule 2: the exact list (`normalise.CONTAINER_RULES`)

| Route | Fields replaced |
|---|---|
| `POST /api/clients/{id}/packages` | body `size_bytes`, `sha256` |
| `GET /api/clients/{id}/artifacts/{artifact_id}` | header `x-content-sha256`; recorded body `length`, `sha256` (the response **is** the container) |
| `POST /channel/v1/tools/claim_package_create_commit` | body `facts.result.size_bytes`, `facts.result.sha256` |
| `POST /channel/v1/tools/claim_package_link` | body `facts.size_bytes`, `facts.sha256`, and the hash **displayed** in the table, `blocks[1].rows[1][1]` |
| `GET /channel/v1/downloads/{ticket}` | header `x-content-sha256`; recorded body `length`, `sha256` |
| `POST /api/v2/program-drafts/{id}/export` | header `x-bundle-sha256`; recorded body `length`, `sha256` |
| `GET /api/v2/program-drafts/{id}/export/manifest` | body `bundle_sha256`, `bundle_bytes` |

The list was completed by searching every recording for every 64-hex string and every `*_bytes` / `size` key: the other hashes in the recordings
(`trail_sha256`, `evidence_hash`, `calculation_id`, `content_sha256`, `approved_sha256`, the per-file `files[].sha256` of the export manifest) hash
JSON or single files, not a container, and were identical on both interpreters. `agents.json` and `orchestrator.json` contain none.

### Rule 2 does not make a hole

* **Shape is verified.** A size is replaced only if it is a non-negative integer as written (`0`, `10009`; not `"10009"`, `-5`, `1.0`, `null`, `true`); a hash only if it is 64
  lowercase hex characters. Otherwise the value is **left as it is** and fails against the placeholder in the recording (`value` or `type`). A missing field fails as `missing-field`.
* **Consistency is verified where the response carries the bytes.** A header hash (`x-content-sha256`, `x-bundle-sha256`) is replaced only if it equals the
  SHA-256 of the body the same response carried; a header that lies about its own body keeps its value and fails.
* **Members are always compared** (`compare.compare_members`): name, uncompressed size and SHA-256 of **each member**, with one diff per member
  (`zip-entry` at `body.zip_entries[<name>]`, `.size`, `.sha256`, or `$order`). A renamed, changed, missing, extra or reordered member, or a response that
  is no longer a zip, is a failure. The container's own bytes are never compared.
* **Only the listed pairs.** A hash or size anywhere else is compared as before. `contract/selftest.py` proves all of this (mutations on the server's answer, before normalisation).
* **Residual, declared:** the displayed hash and the declared hash are not cross-checked against each other across exchanges (e.g. `package.create`'s `sha256` against
  the later download). A port that reports an internally inconsistent but well-shaped hash would pass; the members of the download still have to match.

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

## Interpreter

The recordings are made and verified on **CPython 3.12** (the version the product runs on), pinned in code by `contract/oracle.py`. Evidence that the choice matters only for container bytes: 3.12.13 (zlib 1.3.2) against recordings made on 3.14.2 (zlib-ng 2.2.4): 1,755 / 1,769 exchanges identical, the 14 others being exactly rule 2's fields. The sqlite date adapters in `harness/freeze.py` are needed on both interpreters (the clock is frozen with date subclasses, and sqlite3 looks adapters up by exact type); on 3.12 an assertion at start-up proves they write what the default adapters write. The inventory is canonical across interpreters (`inventory/typenames.py`). The 3.12 recordings pass strict replay on 3.14.2 (1,769 / 1,769) and `capture --check` there is byte-identical, which is why no third rule is needed.

## Proof of determinism

* `capture record` then `capture --check` twice, all 12 recordings byte-identical each time, on 3.12.13 (`docs/capture-log.md`); and once more on 3.14.2 with `--allow-other-python`.
* Replay against a real `uvicorn` (a separate process) and against the in-process harness: 0 differences in strict mode (1,769 exchanges), on 3.12.13 and, as a cross-check, on 3.14.2.
