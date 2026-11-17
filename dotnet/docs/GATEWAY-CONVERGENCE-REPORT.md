# W3 convergence: percentage targets pass; inherited waiver policy remains blocked

## Result and evidence boundary

Both merged executables run independently and repeatably. The standalone
gateway already composes the API's application/runtime services in-process;
the reported missing-API problem did not reproduce on the supplied branch.
No extra API process, service registration or package was needed.

Fixed governed-query refusal ordering/metadata, anonymous HTTP attribution and
finding-history timestamp rendering. Added an unattended dual-host replay
runner and a read-only policy audit. **No comparison, recording, threshold,
calculated figure or valid authenticated authorization outcome was changed.**

Strict build and format pass; **1,551 fast tests pass**, zero failures/skips.
All nine API and three gateway scenarios execute through the public semantic
replay. There are **1,769 recorded steps, including four controls**.

All six named replay percentage targets pass in the local W3 policy audit.
**Unconditional convergence is not claimed:** framework still relies on
**9/17 waived cases (52.94%)**, above the inherited 25% waiver limit.
`INHERITED-W3-RELEASE-BLOCKERS.md` preserves that Stage-4 policy stop. W2 explicitly disclosed
the same conflict and noted that its latest external conductor did not flag
the share; this session neither assumes that silence changes the cap nor
changes a comparator to make it disappear.

No live Fabric, Foundry, Entra, customer access or model generation was used.
The source is the hermetic synthetic seed. No heavy/live-suite result is newly
claimed; the task's required local test gate excludes heavy tests.

## Baselines and final boards

The supplied failure summary reported gateway **83/255 (32.5%)** against a host
whose non-gateway routes also failed. Running the correct two independent
executables on the actual merged branch instead produced the following fresh
baseline. That supplied summary is not substituted for measured evidence.

Both columns below use the **same current policy audit and existing register**.
Pass counts include fully registered cases, not only exact raw matches.
No new waiver entry was added.

| Group | Fresh baseline | Final | Required | Final waived |
|---|---:|---:|---:|---:|
| framework | 17/17 (100.00%) | 17/17 (100.00%) | 90% | 9/17 (52.94%) |
| reads_calc | 406/414 (98.07%) | 406/414 (98.07%) | 95% | 26/414 (6.28%) |
| claims_artifacts_rules | 291/316 (92.09%) | 295/316 (93.35%) | 90% | 70/316 (22.15%) |
| drafts_runs | 313/323 (96.90%) | 313/323 (96.90%) | 90% | 68/323 (21.05%) |
| ai | 27/27 (100.00%) | 27/27 (100.00%) | 90% | 3/27 (11.11%) |
| gateway | 233/255 (91.37%) | 236/255 (92.55%) | 90% | 11/255 (4.31%) |

Other groups remain visible: sealed workspace **79/96**, unassigned **238/317**.
They are not recast as implemented gateway operations or hidden from the board.

| Raw replay | Scenarios | Steps | Baseline differing fields | Final differing fields |
|---|---:|---:|---:|---:|
| API executable | 9 | 1,514 | 2,325 | 2,311 |
| Gateway executable | 3 | 255 | 528 | 523 |
| Total | 12 | 1,769 | 2,853 | 2,834 |

Raw replay intentionally still exits 1. Its comparator includes differences
which policy permits. These are execution-complete comparisons, **not claims
of zero-difference replay or an external conductor run**.

Baseline evidence: `artifacts/w3-baseline-fast`,
`artifacts/w3-baseline-replay/{api,gateway}/replay.json` and
`artifacts/w3-baseline-replay/policy-board.json`.
Final evidence: `artifacts/w3-final-fast`,
`artifacts/w3-final-replay/{api,gateway}/replay.json` and
`artifacts/w3-final-replay/policy-board.json`.
The policy board records raw-report SHA-256 values, every unresolved field,
register hits and category/path clusters.

## Repairs and regression evidence

| Repair | Cause and implementation | Evidence |
|---|---|---|
| Governed refusal ordering | An empty employee question was classified as a raw-person request before validating whether it asked for anything. Validate empty selection first. Distinct-value requests now validate columns before raw-row lane checks. | Four new fast cases prove empty, unknown, blocked and non-category refusals, actionable field metadata and no provider execution. |
| Distinct error contract | Unknown columns incorrectly returned `column_not_listable` and omitted `error.field`. Unknown, blocked and known non-category columns now retain their separate typed 422 refusals and `field: column`. | MCP empty query, MCP unknown distinct column and REST unknown distinct column now pass. No valid-row access outcome changed. |
| Anonymous HTTP attribution | Claims, engagements and findings used the internal `system` fallback for an anonymous local HTTP person. Their shared HTTP defaults now say `anonymous`; explicit engine/package/practitioner defaults remain. | A new ordinary-host test proves all three decision surfaces and supplied local attribution. Authenticated principal precedence is unchanged. |
| Finding timestamps | SQLite's six-zero timestamp padding leaked through the string hydrator. Hydrate the stored supersession as an instant and render its canonical ISO representation. | Existing durable/reopen/tenant test now runs at zero and nonzero microseconds, checks the exact timestamp after reopening storage, and retains the audit assertions. No stored timestamp changes. |
| Repeatable dual-host execution | Old documentation described deferred business routes and a manual/obsolete profile reset. Added `run_wave_replays.py` and corrected `HOST-ARCHITECTURE.md`. | Full baseline, post-fix and final public replays; isolated stores, health checks, actual marker-based ordinary launches and owned-process cleanup. |

The first new query regression exposed that a token column still hit a lane
check before distinct validation. Correcting that ordering made all four new
cases pass. An attribution-test build initially reported `IDE0055: Fix
formatting`; the existing formatter corrected the test, with no suppression.
No stale shared test, duplicate registration or package conflict reproduced
in the initial strict build or 1,545-case merged fast baseline.

The guarded query fix was committed as `55ef830`; the shared decision metadata
fix as `1d6cc19`. Each implementation commit followed a passing strict build,
format verification and complete fast suite.

## Policy audit, not a replacement comparator

`wave_replay_report.py` reads unchanged raw reports and applies existing exact
route ownership, with every `g1_` scenario assigned to gateway as instructed.
It reuses the already tested free-text tolerances and exact register matching.
It permits only the explicitly approved F-18 operational preview counters to
differ numerically. Numeric JSON figures, money strings and identifiers are
not waived. Successful tool narration is not treated as error wording.

The historical `convergence_board.py` remains unchanged. It predates the F-18
exception and rejects three registered native documentation bodies because a
generic regex finds different digit substrings in HTML. Its stricter framework
score remains **14/17 (82.35%)**, not secretly rewritten. The new audit treats
only registered native `/docs`, `/redoc` and OAuth-redirect **HTML documents**
as framework markup, as the W2 conductor did; it does not apply that treatment
to JSON, tool facts, other routes, statuses or missing fields.

Three new policy-boundary tests and twelve existing policy/setup tests pass.
They prove the distinction between registered HTML and numeric JSON, exact
F-18 counter paths, same-code MCP error wording, and schema/status preservation.
This audit is explicitly local and does not claim to be the external
conductor's implementation.

`improvements/integrate-W3.json` is intentionally empty: all production changes
restore the recorded intended contract. No duplicate `converge-w3.json` was
added; the fixed session-named register rule takes precedence. Existing
gateway, W2 and orchestrator registers remain unchanged.

## Remaining clusters

These are field differences after policy processing, not independent defect
counts. Missing fields following a status refusal are counted individually.

| Group | Failed cases | Fields | Principal clusters |
|---|---:|---:|---|
| gateway | 19 | 49 | Two person-lane refusals, two catalogue results, fifteen later-identity cases |
| reads_calc | 8 | 148 | Six unavailable-client/bounded-limit statuses; two later-run-ID/money-scale cases |
| claims_artifacts_rules | 21 | 100 | Later claim IDs, four status envelopes, zero-year coverage metadata |
| drafts_runs | 10 | 19 | Seven ID/base-year-durability cases, state-filter status, two stored-program item cases |
| framework | 0 | 0 | Percentage passes; 9/17 registered cases still exceed the inherited waiver cap |
| ai | 0 | 0 | None under the stated global free-text policy |

### Gateway: exact cluster attribution

- **Person lanes: two MCP cases / sixteen fields.** `call.client_at_risk.typical`
  and `call.findings_list.typical` return
  `employee_level_not_allowed` where Python supplied unmarked person-derived
  facts. Missing facts are not waived. The existing application lane checks
  and metadata are unchanged; reconcile privacy design versus valid-request
  authorization preservation with the owner before changing access.
- **Catalogue: two cases / seventeen fields.** REST and MCP advertise eight
  implemented warehouse datasets rather than eleven including raw `payroll`,
  `location` and `pay_code`. Those three lakehouse governed-query bindings are
  not implemented. Counts/list differences remain unwaived; no availability,
  source data or successful empty aggregate was fabricated.
- **Genuine identities: fifteen cases / sixteen fields.** Seven confirmation
  IDs, six correlation bodies, one correlation header and one package
  artifact/download-path pair differ after genuine allocation histories diverge.
  Python previews allocate temporary claim IDs; .NET pure previews do not.
  No dummy ID draws, response rewriting, removed audit durability or UUID
  waivers were introduced.

The rate-limit scenario passes **10/10**; MCP passes **100/103**; REST passes
**126/142**. Initialize, session ownership, minted-token calls, typed errors,
single-use downloads, numeric guard and existing gateway/orchestrator tests
remain exercised. Passing these counts does not certify unresolved tool
results as tier-A equivalent.

### Other shared work and owner decisions

Native long claim/engagement program codes and rule-verifier names still exceed
storage bounds where Python accepted them. Resolve the storage/validation
contract; do not silently truncate valid values or waive their 500s.
Unavailable portfolio still returns 503 instead of the recorded degraded-200
envelope. Zero tax year is filtered rather than treated as absent.

Keep the inherited money-string-scale decision explicit: native DECIMAL4
text and recorded shorter strings are not interchangeable. The remaining
base-year durability and stored batch-program values are not preview counters
and do not receive F-18 waivers.

Figure-sensitive M-01 ingestion precedence and first-program multi-program
pricing remain unchanged. M-01 conflicts with year-pack precedence; changing
it requires owner reconciliation, not a gateway fix. Row-count/max-modified
fingerprints remain observations, not immutable source snapshots.

Cross-replica idempotency reservation, uncertain-write recovery protocol,
workflow retention/durability, trusted orchestrator ingress/employer binding,
live grants and publication, provider fiscal/decimal behavior and optional
orchestrator safety off-switches remain the explicit W3 handoff limitations.
No new result-recovery API, storage guarantees or external-system proof was
invented.

## Reproduction

From this worktree root:

```powershell
dotnet build .\dotnet\TaxCredit.slnx -warnaserror --nologo -v:q -m:1 -nr:false
dotnet format .\dotnet\TaxCredit.slnx --verify-no-changes --no-restore -v:q
dotnet test .\dotnet\TaxCredit.slnx --no-build --no-restore --filter 'Category!=heavy' -m:1 -nr:false
& C:\Projects\py312-oracle\.venv\Scripts\python.exe .\dotnet\docs\run_wave_replays.py --out .\dotnet\artifacts\w3-replay
& C:\Projects\py312-oracle\.venv\Scripts\python.exe .\dotnet\docs\wave_replay_report.py --raw .\dotnet\artifacts\w3-replay\api\replay.json --raw .\dotnet\artifacts\w3-replay\gateway\replay.json --out .\dotnet\artifacts\w3-replay\policy-board.json
```

The root selects SDK 11.0.100; all projects still target net10.0 and use no
newer/preview feature. The solution's prescribed SDK 10.0.404 is selected when
running inside `dotnet`. CPython 3.12.13 is the oracle, with this checkout's
`contract` and `backend` selected by the runner. No package was added.

Both replay hosts are bounded owned child processes and are stopped in
`finally`. Changes are confined to `dotnet`; commits are local. Nothing was
pushed and no remote or other worktree was changed.
