# W2 route convergence

## Outcome: HALT, not a successful cutover gate

The shared composition, deterministic-source and cross-feature integration
repairs are implemented. All twelve recorded scenarios executed. Reads, claims
and AI meet their thresholds; framework and drafts do not. Stage 4 requires an
honest halt rather than reproducing framework accidents, fabricating counters,
discarding durable state or waiving numeric differences.

This report uses the local policy diagnostic over the unchanged semantic
replay reports, not a claimed execution of the external conductor. The older
`replay_board.py` groups some operations loosely and prints obsolete green
labels; those labels are not evidence of gate success.

## Resumed conductor failure: actual setup repaired

The resumed task supplied a new conductor board: framework 17/19 (89.5%,
nine waived), reads 367/414 (88.6%, 114 waived), claims 241/316 (76.3%,
61 waived), drafts 205/323 (63.5%, 43 waived), AI 26/27 (96.3%, three
waived). Framework and reads exceeded the waiver cap. The conductor's raw
semantic report contained 5,740 failing fields; its policy board separately
reported 3,754 after its own policy processing. These are different measures.

Inspection of the conductor's actual raw exchanges established the missing
boundary: the public external `contract.replay --reset-url` path sent only
`{}` before each scenario. It never selected P2 or installed the auth scenario's
mode. Earlier local checks had prepared both outside that path, so their setup
was correct but the conductor did not run it. This was an integration defect,
not evidence that the extra conductor failures should be waived.

Commit `9a1ffd2` moves that setup into `contract\replay_setup.py`, called by the
actual external replay command before token minting or any recorded request.
Reset now receives the declared profile, followed by auth mode, writer
enforcement, audience/tenant fixture configuration and the scenario's rate
limit through the existing control hooks. The auxiliary runner delegates to
that same public path; it no longer has a separate preparation implementation.
Preconfigured external servers without `--reset-url` remain untouched.

The direct complete replay was then run on **one isolated ordinary host**,
using `backend` as cwd, the approved interpreter, `--mode semantic`,
`--base-url` and `--reset-url`. All twelve scenarios completed:

| Raw scenario | Conductor before | Corrected direct replay |
|---|---:|---:|
| p1_auth | 1,029 failing fields | 182 |
| p2_reads_writes | 888 | 148 |
| p2_run_batches | 498 | 215 |
| Other nine scenarios | Unchanged | Unchanged |
| All scenarios | 5,740 | 3,870 |

The corrected one-host reports reproduce the previous independently prepared
scenario results exactly: group totals, every unresolved field and every
rejected numeric waiver. This establishes the corrected setup without changing
an expected response, comparator, threshold or runtime handler.

Current evidence is under `dotnet\artifacts\integrate-resume-external`:
`replay.json` / `replay.log` are the direct unmodified replay output and
`policy.json` is the separately identified diagnostic. The stricter local
diagnostic below still fails framework and drafts. In particular it rejects
the three numeric HTML matches the supplied conductor board had accepted;
neither board is silently substituted for the other.

Five new external-setup regressions cover P2/auth setup, ordering before each
scenario, setup failure propagation, restoring unauthenticated mode and leaving
a no-reset preconfigured server alone. Together with the existing three policy
and two report-output regressions, all ten Python checks pass. Strict .NET
build/format and all 978 fast tests pass again. The initial no-build test
attempt aborted in VSTest host initialization; rebuilding local metadata
resolved it without dependency, test or runtime changes.

## Comparable before and after

Both columns below rescore actual baseline/final replay output using the same
final register, exact method/template ownership and documented text tolerances.
Pass counts include accepted registered cases. The waiver limit is 25% of a
group's cases, independently of its percentage threshold.

| Group | Baseline | Final | Required | Final waived | Result |
|---|---:|---:|---:|---:|---|
| framework | 14/19 (73.68%) | 14/19 (73.68%) | 90% | 6/19 (31.58%) | Percentage and waiver cap fail |
| reads_calc | 370/414 (89.37%) | 406/414 (98.07%) | 95% | 26/414 (6.28%) | Meets both |
| claims_artifacts_rules | 250/316 (79.11%) | 291/316 (92.09%) | 90% | 70/316 (22.15%) | Meets both |
| drafts_runs | 250/323 (77.40%) | 287/323 (88.85%) | 90% | 42/323 (13.00%) | Percentage fails |
| ai | 15/27 (55.56%) | 27/27 (100.00%) | 90% | 3/27 (11.11%) | Meets both |

Other recorded ownership buckets remain visible, not omitted from the replay:
gateway 0/251 (deferred mock gateway), workspace_sealed 79/96 (82.29%, three
waived), and unassigned 240/319 (75.24%, no waivers). They are not additional
success claims or substitutes for the five required groups.

The task's supplied earlier conductor baseline was 63.2%, 80.2%, 54.7%, 50.8%
and 63.0% respectively. It used the then-current register/scoring context and
must not be confused with the identically rescored local baseline above.

There are **1,769 recorded steps: 1,765 HTTP exchanges and four scenario
controls**. The supplied group denominators sum to 1,765, although the task's
earlier summary calls all 1,769 exchanges.

Evidence, relative to `dotnet\artifacts`:

- `integrate-policy-baseline-final.json`: comparable baseline.
- `integrate-policy-final.json`: final groups, category/path clusters, every
  unresolved field and rejected numeric waiver.
- `integrate-convergence-final\raw\*.json`: unchanged actual replay reports.
- `integrate-convergence-final.log`: all twelve scenarios completed. Runner
  exit zero means execution completed, not semantic convergence.

## Repairs and regression evidence

| Repair | Why it was needed | Evidence |
|---|---|---|
| Dynamic stub selection and removal of obsolete duplicate probes | Implemented routes no longer return 501; test probes must not shadow production endpoints | Framework discovery/replacement tests retain single-endpoint and pre-build service-registration assertions; initial ten fast failures eliminated |
| Production feature discovery in provider tests; source reference-data binding | Constructing a second partial runtime graph omitted sibling collaborators | Provider binding tests compose the actual discovered modules; source reference data comes from committed synthetic fixtures |
| Scoped mediator and artifact leases | Scoped collaborators could not safely live below a singleton mediator | Runtime scope/lease regressions; no service-location workaround |
| Actual section-9 validation query collection | Runtime reported 17 where the recorded query contract contains 20 | Twenty real queries, with nine supplemental integrity checks retained; no literal counter patch |
| Recorded page-sensitive list metadata | A page-independent redesign changed client-visible totals | Existing read paging/filter tests and full replay; the recorded semantics are retained |
| Source-backed portfolio footprint and fixture display name | An unbound sibling reader hid known source states | Actual source states/priceable coverage, with precise array-shape register entries; no invented population |
| Canonical AI sibling reads | The merged AI feature still lacked its page/read collaborators | Ordinary-host book, eligibility and portfolio/unit/employee-summary regressions; final AI 27/27 |
| Ready-boundary deterministic-source restoration | Stored identifiers omitted four real OpenTelemetry startup allocations | Independent P1/P2 exports record UUID counters 7/30 and zero secret draws; all other manifest fields/table hashes unchanged |
| Deterministic rule metadata clock | Filesystem mtimes differed from the recorded metadata protocol | Documented frozen-clock/path-CRC32 protocol only in contract mode; ordinary hosts still read actual mtimes |
| Initial assessment identity uses its injected sources | An outer sink rewrote identity and left initial/refreshed allocation order inconsistent | Assessment regression asserts genuine initial and refreshed IDs; no pricing changes or dummy draws |
| Capability envelopes distinguish reads from writes | Blanket POST classification denied an acting reader's book query | Signed-agent reader book succeeds; engagement preparation remains 403 `not_authorized` |
| Unavailable nonpositive reads return JSON 404 | Global positivity binding masked the handler's unavailable-client semantics | Progress/forecast/ingestion regressions for zero and negative selections; Int64 overflow and positive SQL identity guards remain |
| Explicit SSE UTF-8 and dictionary error type | Transport metadata and wrong-body error classification disagreed | Stream frame/data checks retained with exact charset assertion; invalid dictionary produces 422 `dict_type` |
| Heavy integration fixtures exercise the real merged services | Old probes assumed public draft listing, accepted duplicate creation, and omitted new reset tables | Reader/writer draft-list assertions, distinct second draft creation, all-22-table population, reset publication/observation checks and zeroed write sequence |

No package was added. The domain change only invokes existing identity/clock
delegates when constructing the initial priced claim; no certified arithmetic
was re-ported or changed. F14 valid-request authorization exceptions remain
explicitly tested.

Implementation commits before the final runtime-boundary repair:
`15e9218` (shared fixtures), `32181ce` (scoped collaborators/metadata),
`5b213e9` (exported deterministic sources), `232dd39` (runtime boundaries) and
`9a1ffd2` (actual external replay setup). The machine-readable status pins the
verified replay repair; the documentation commit follows it.

## Register integrity

`improvements\integrate-W2.json` contains 34 precise entries:

| IDs | Scope |
|---|---|
| 1 | Offline `chat.ask-client`: canonical authorized facts instead of an unrelated fixed demonstration |
| 2-9 | Eight explicit `items[0..3].states` / `priceable_states` array-length paths only |
| 10 | Invalid state-as-scope request: JSON 422 instead of unhandled enum-conversion 500 |
| 11-13 | Native docs, reference and OAuth-redirect HTML |
| 14 | Configured CORS allow-list instead of arbitrary-origin wildcard behavior |
| 15 | Native boolean error-code naming on invalid portfolio input |
| 16-34 | Route-specific native request-binding error metadata, only under `detail[0].` |

Retired eleven broad source/AI/persistence waivers about behavior not exercised
by their matching exchanges, three inert duplicate persistence entries whose
categories were scenario names, and the obsolete draft-ID waiver. Their
underlying durability/security fixes were not removed.

Three HTML waiver matches are **rejected**, not accepted:
`p1_auth:none.docs`, `p1_reads:framework.docs`, and
`p1_reads:framework.redoc`. Different numeric fragments in `body.text` trigger
the unchanged numeric prohibition. Even accepting all three would yield
17/19 (89.47%), still below 90%, with 9/19 (47.37%) waived. No comparator,
threshold, recording, certified constant or numeric prohibition was weakened.

The diagnostic's additional error-text paths (`detail.detail`,
`error.message`) apply only to error-status scalar wording. Missing fields,
schema/status differences and successful values remain real failures. Its
three regression tests cover these boundaries.

## Remaining clusters

These are failed exchanges, not independent defect counts. Field counts include
the downstream missing/extra fields caused by a status mismatch. Full exact
paths and case IDs remain in `integrate-policy-final.json`.

| Group | Failed cases | Unresolved fields | Principal categories/paths |
|---|---:|---:|---|
| framework | 5 | 12 | Three `value body.text`; two `status status`; seven downstream header/body/schema fields |
| reads_calc | 8 | 148 | Six status/shape cases; remaining run IDs and exact monetary-string scale, including `installments[].claimable_usd` |
| claims_artifacts_rules | 25 | 114 | Claim IDs, attribution, four status envelopes, zero-year filter totals, one history timestamp |
| drafts_runs | 36 | 239 | Durable latest-run/default-program previews, run/draft/override IDs, base-year durability and one wrong-method outcome |
| ai | 0 | 0 | None |

### Framework: ownership and artifact policy conflict

Two `g1_rest` recordings expect 404 at `/docs` and `/openapi.json`, while the
ordinary API correctly serves its documented endpoints. Exact operation
ownership puts those exchanges in framework, even though gateway is deferred.
Do not vary API behavior by scenario/caller. The other three failed cases are
the rejected documentation-HTML matches above. Six already accepted framework
waivers alone exceed the cap. The owner must resolve replay server ownership
and the framework-artifact/cap policy; this run does not change either.

### Reads: 8 cases

Six status cases comprise unit/employee reads for client zero or negative
(recorded 200, now unavailable 404) and two enormous unit-list/detail limits
(recorded 200, bounded 422). The employee recording's permissive CSV fallback
must not leak another client's data. The remaining two cases are
`p1_auth:reader.read-units` and `p1_writes:ok.post-api-employee-drill`, affected
by later run-ID allocation and native DECIMAL4 formatting. For example,
`"3500.0"` and `"3500.0000"` are different contractual money strings, not
interchangeable number lexemes. No scale waiver or float conversion was used.

### Claims: 25 cases

The disjoint case breakdown is 16 identity-drift cases (some also attribution),
three attribution-only, four status cases, one zero-tax-year coverage-filter
case and one timestamp case.

Early assessment/run identities now match. Later allocations still diverge:
the .NET finding repository persists a real separate finding-audit record
where Python's SQLite implementation has no separate audit UUID. Lookup
verification paths also warrant tracing; the exact first extra allocation
after the repaired boundary is **not fully established**. Removing real audit
writes or consuming dummy IDs is not an acceptable fix.

Three long-text storage cases return 500 where Python accepted the value:
claim `program_code` (expected 201), engagement `program_code` (expected 200)
and rules-verification `verified_by` (expected 200). Native column bounds versus
permissive input need a deliberate storage/contract decision; this is not a
valid-value-loss waiver.

Ordinary feature backlog remains explicit: default `"anonymous"` versus
`"system"` attribution, unavailable-portfolio 503 versus recorded degraded-200
envelope, `tax_year=0` filtering versus Python truthiness, and missing fractional
seconds versus `.000000` in finding history. These are not claimed improvements.

### Drafts: 36 cases

Twenty-eight cases are tied to durable latest-manifest/default-program plan
semantics: five P1 batch previews and 23 P2 batch/list/item exchanges. Recorded
disconnected latest-run storage reports `never_run:1` / `none_yet`; the real
durable manifest reports zero / `all_years`. P2 plans also change
`program_code:null` / `programs.none` to resolved `GA_JTC`. The other seven
identity/base-year-durability cases and one batch wrong-method variant remain
unmatched.

F18 can document genuine durable latest-run behavior, but cannot waive a
changed `never_run`, other count or identifier. Neither invented previews nor
severing durable manifests would be honest convergence.

## Verification and operating boundary

All commands ran locally in this worktree on branch `dotnet/integration`.
SDK 10.0.404 targets net10.0. The approved oracle is
`C:\Projects\py312-oracle\.venv\Scripts\python.exe`, CPython 3.12.13, importing
this checkout. Replay uses `backend` as its working directory, worktree-root
`PYTHONPATH`, `CONTRACT_PYTHON` pointing to that interpreter and `--mode semantic`.
Each scenario gets its actual P1/P2 reset, tokens, environment and an isolated
ordinary local host; owned hosts are terminated afterwards.

Final warning-as-error build has zero warnings/errors; format verification
passes. All 978 fast tests pass. The full heavy run produced 137 passed and four
fixture failures out of 141, without skips. A targeted four-case repair run
passed both P2 cases, and the final fast-plus-two-heavy run passed all 980 cases.
Every original heavy failure has a passing targeted result: all 141 distinct
heavy cases are verified across these runs, not an initially green monolithic
run. Three diagnostic tests also pass.

Evidence: `integrate-final-build.log`, `integrate-final-format.log`,
`integrate-final-fast`, `integrate-convergence-heavy`, `integrate-heavy-repair`
and `integrate-final-repair` under `dotnet\artifacts`. The final command was
`dotnet test --no-build --filter 'Category!=heavy|FullyQualifiedName~Writer_enforcement_rebuilds_and_resets|FullyQualifiedName~P1ResetClearsEveryOperationalTable' -m:1 -nr:false`.
Only the two P2-heavy HttpClients received five-minute fixture timeouts;
production limits and semantic assertions were unchanged.

No live Fabric, Foundry, Entra or customer system was contacted. No Python
product, recording, certified fixture, remote or package dependency changed.
All commits are local; nothing was pushed.

On resume the .NET gates were repeated: `integrate-resume-build.log` has zero
warnings/errors, `integrate-resume-format.log` records format verification and
`integrate-resume-built-fast` contains 978 passing tests without skips. The
previous 141 distinct heavy-case results remain applicable: this repair changes
only the external replay harness and its helper/tests, not .NET production or
heavy fixture behavior. No new improvements entry is needed for correct
scenario setup, because it introduces no deliberate product difference.

## Decisions carried forward

See `HALT-integrate-W2.md` and `status\integrate-W2.json` for the owner work
list. Besides the concrete remaining clusters, preserve the pre-existing
figure-affecting candidates: M01 ingestion overrides of year-resolved wage
basis/measuring dates/pay codes, and first-program credit pricing in a
multi-program state. M01 contradicts ADR-005's prohibition on overriding
year-resolved statute, but the explicit task policy still requires preserving
it until the owner approves a figure-affecting correction. Neither was changed.
SQL row-count/max-modified source
fingerprints are observations, **not immutable Delta snapshots**; an owner must
accept that limitation or select a stronger version source.
