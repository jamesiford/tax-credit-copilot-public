# W2 route convergence

## Outcome: five replay percentage thresholds met under the updated policy

The owner's latest task adds `durable_manifest_counts`: operational batch
preview counters must follow real durable manifests, and exact registered
differences from the disconnected recording store are permitted. Applied that
decision without changing a handler, response, comparison, test or threshold.
The prior HALT marker is retired; its evidence remains in the history below.

Fresh full direct replay completes **12 scenarios / 1,769 steps** and exactly
reproduces all **3,870 raw failing fields** in the supplied conductor report.
The additional exact registrations cover **220 fields in 26 fully resolved
draft cases**. Applied to that unchanged official board, drafts rises from
**286/323 (88.5%) to 312/323 (96.6%)**, with **68/323 (21.1%)** waived,
below the 25% batch-group limit. This is a verified registered-only projection,
**not a claim that the external conductor has run again after the commit**.
Its remaining field count projects from 2,113 to 1,893; raw replay is not
claimed to have zero failures.

| Group | Supplied conductor | After exact registrations | Required | After waived |
|---|---:|---:|---:|---:|
| framework | 17/17 (100.0%) | 17/17 (100.0%) | 90% | 9/17 (52.9%) |
| reads_calc | 406/414 (98.1%) | 406/414 (98.1%) | 95% | 26/414 (6.3%) |
| claims_artifacts_rules | 291/316 (92.1%) | 291/316 (92.1%) | 90% | 70/316 (22.2%) |
| drafts_runs | 286/323 (88.5%) | 312/323 (96.6%) | 90% | 68/323 (21.1%) |
| ai | 26/27 (96.3%) | 26/27 (96.3%) | 90% | 3/27 (11.1%) |

The latest supplied conductor reports only drafts below threshold. Its
framework group now has 17 cases, no failing cases and 52.9% waived, with no
framework gate failure. That waiver share remains visible and is **not**
claimed below 25%; this session changes neither framework policy nor grouping.
Other buckets remain gateway 2/255, sealed workspace 79/96 and unassigned
238/317. These are not claims of gateway completion or full literal parity.

### Exact policy application and integrity

Commit `cd1f137` adds **51 exercised entries**, IDs 35-90 excluding
37, 68, 73, 78 and 88, to `improvements\integrate-W2.json` (85 total).
Every new entry is an exact route/category/path registration:

- **35 F18 entries / 158 fields** cover `never_run`, `skip_coverage`,
  `skip_candidates_upper_bound` and the corresponding sampled last-run state
  and added metadata. Preview, accepted batch detail, cancel/retry and the
  three observed list positions retain the same truthful accepted summary.
  Exactly **36 numeric field matches** are authorized operational
  `never_run` or `skip_candidates_upper_bound` differences.
- **16 source-binding entries / 62 fields** separately cover missing
  `programs.none` and added `programs.GA_JTC` map keys. The Python design in
  `application/runs/pairs.py` resolves programs from payroll footprint; its
  independently unconfigured recording reader lost that footprint. The
  already-correct merged source resolves actual authored coverage. These
  entries cover only missing/added keys, **not changed existing program counts**,
  work-item identities, stored item program values or calculated figures.

Five unexercised candidate registrations were removed before committing.
Boundary checks prove the additions do not cover changed existing last-run
IDs, client/item populations, execution success counts, existing program
counts, statuses or certified eligibility figures. The 26 resolved cases have
no remaining raw field differences after existing official waivers, `Vary`
tolerance and these precise additions; **no extra free-text tolerance or
changed numeric comparison is needed**.

Verification evidence is under
`artifacts\integrate-durable-policy-external`: unchanged `replay.json`,
`replay.log`, exact-conductor `confirmation.json` and `registration-audit.json`.
The audit starts from the actual supplied board, retains every other group
verbatim and records every new entry hit and fully resolved case. It also
reproduces the official drafts baseline exactly (37 failed cases / 240 fields)
before applying only the new registrations (11 failed cases / 20 fields).
The old
`convergence_board.py` retains its earlier policy and is historical, not the
updated conductor gate or the basis of the projection.

Strict build has zero warnings/errors; format passes; **978 fast tests**
pass with no failures/skips, and **ten Python setup/diagnostic tests** pass.
Logs/TRX files use `artifacts\integrate-durable-policy-*`. No .NET runtime,
test or dependency changed, so the existing 141 distinct heavy-case passing
results remain applicable. The single isolated replay host was health-checked
and stopped in `finally`. Nothing was pushed.

### Remaining non-gating differences

Retaining all other official failures leaves **11 draft cases / 20 fields**:
seven identity/base-year durability cases, one state-filter status case, two
work-item program-code cases and `p2_run_batches:unknown-client` at
`detail.detail` (the native error omits the echoed unknown client).
The earlier local diagnostic tolerates that last wording difference and has
ten such cases / 19 fields; its extra text tolerance is not used to claim
another official pass. IDs, status outcomes and work-item stored program values
were not waived.
Reads retains eight failures, claims 25 and AI one, all visible within their
passing percentage thresholds. Existing owner work for exact money scale,
later genuine ID allocation, valid long-text storage, M01, first-program
pricing and source-version strength remains below-threshold backlog, not
silently resolved work.

## Historical: official conductor confirmation before the policy update

The task was resumed again with the conductor report generated on 16 November
2026 after the setup repair. Its actual raw report has **3,870 failing fields**,
and every ordered failure in every scenario is identical to the previous
corrected direct replay. This confirms that the public reset/profile/auth fix
is now exercised by the conductor. The new percentages are not a runtime
regression or a different reset world.

| Group | Official pass | Required | Official waived | Result |
|---|---:|---:|---:|---|
| framework | 17/19 (89.5%) | 90% | 9/19 (47.4%) | Threshold and 25% cap fail |
| reads_calc | 406/414 (98.1%) | 95% | 89/414 (21.5%) | Meets both |
| claims_artifacts_rules | 279/316 (88.3%) | 90% | 70/316 (22.2%) | Threshold fails |
| drafts_runs | 225/323 (69.7%) | 90% | 43/323 (13.3%) | Threshold fails |
| ai | 26/27 (96.3%) | 90% | 3/27 (11.1%) | Meets both |

The official policy board has **2,187 remaining fields** after 573 registered
fields and 1,110 tolerated free-text fields are removed from the 3,870 raw
failures. Its other buckets remain gateway 0/251, sealed workspace 79/96 and
unassigned 240/319. All 1,769 recorded steps completed.

| Required group | Official failed cases | Remaining fields | Difference from local diagnostic |
|---|---:|---:|---|
| framework | 2 | 9 | Official scoring accepts three HTML matches rejected by the local numeric guard |
| reads_calc | 8 | 148 | Same failed cases; different waiver accounting |
| claims_artifacts_rules | 37 | 126 | Twelve additional cases differ only in scalar `detail` wording |
| drafts_runs | 98 | 302 | Sixty-two additional wording-only cases: 39 `detail.reason`, 22 `detail`, one `detail.detail` |
| ai | 1 | 1 | One additional `error.message` wording-only case |

Tier C permits error-message wording to differ, but the official scorer does
not remove all those scalar paths. This report records that distinction rather
than copying Python wording, adding broad waivers, or changing the comparison.
Even the more permissive local diagnostic still fails framework and drafts.
In particular, resolving wording alone cannot satisfy all required gates.

No new product or harness change is justified by this resume: the actual raw
evidence exactly reproduces the already investigated stopping condition.
Framework's two cross-server documentation cases, its waiver-cap conflict and
the durable-preview numeric differences below still require owner decisions.
The required Stage-4 HALT is retained; no overall convergence is claimed.

A fresh full direct replay on one isolated ordinary host confirms **12
scenarios, 1,769 steps, 3,870 raw failures and 16,711 semantically tolerated
fields**, with every ordered failure exactly equal to the latest conductor.
Evidence is `artifacts\integrate-conductor-confirm-external\replay.json`,
`replay.log` and `confirmation.json`. The owned host was health-checked and
stopped in `finally`. Strict build and format pass again; all 978 fast tests
and ten Python regressions pass. The corresponding fresh logs/TRX files use
the `integrate-conductor-confirm-` prefix. No .NET runtime or heavy fixture
changed, so the existing 141 distinct heavy passing results still apply.

## Historical: earlier resume and actual setup repair

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

Evidence for that checkpoint is under `dotnet\artifacts\integrate-resume-external`:
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

## Historical: comparable runtime before and after

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

## Historical: runtime repairs and regression evidence

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

## Historical: register integrity before the owner policy update

At that checkpoint, `improvements\integrate-W2.json` contained 34 precise entries:

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

## Historical: remaining clusters before the owner policy update

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

## Historical: runtime verification and operating boundary

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

See `status\integrate-W2.json` for the remaining owner work list; the active
HALT marker was retired after the policy update documented above.
Besides the concrete remaining clusters, preserve the pre-existing
figure-affecting candidates: M01 ingestion overrides of year-resolved wage
basis/measuring dates/pay codes, and first-program credit pricing in a
multi-program state. M01 contradicts ADR-005's prohibition on overriding
year-resolved statute, but the explicit task policy still requires preserving
it until the owner approves a figure-affecting correction. Neither was changed.
SQL row-count/max-modified source
fingerprints are observations, **not immutable Delta snapshots**; an owner must
accept that limitation or select a stronger version source.
