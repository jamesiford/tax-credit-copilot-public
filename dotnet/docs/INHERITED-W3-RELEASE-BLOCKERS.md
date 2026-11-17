# Inherited W3 release blockers

The W3 policy-stop record below is preserved as release-blocker evidence after
the W4 conductor requested removal of the inherited halt-file gate failure.
This documentation relocation does **not** resolve the stop, authorize release,
change the framework waiver cap or supersede any owner decision. W4 deployment
assets remain separate from application convergence approval. The historical
W3 status retains its failed policy/no-halt claims; its report link now points
here so the evidence remains accessible.

---

# Stage-4 policy stop: inherited framework waiver cap

## What happened

All specified replay **percentage** targets pass in a fresh local policy audit
over two complete ordinary-host semantic replays. Build/format and all
**1,551 fast tests** pass. Full unconditional convergence is not claimed:
framework has **9/17 waived cases (52.94%)**, above the inherited **25%** limit.
W2 already disclosed this conflict. Its latest conductor did not flag the
share; no decision here treats that silence as permission to change a cap.

This is the task's Stage-4 gate/policy stop, not an assertion that three failed
implementation attempts or an external-system hard stop occurred.

| Group | Fresh baseline | Final | Required | Final waived |
|---|---:|---:|---:|---:|
| framework | 17/17 | 17/17 (100.00%) | 90% | 9/17 (52.94%) |
| reads_calc | 406/414 | 406/414 (98.07%) | 95% | 26/414 (6.28%) |
| claims_artifacts_rules | 291/316 | 295/316 (93.35%) | 90% | 70/316 (22.15%) |
| drafts_runs | 313/323 | 313/323 (96.90%) | 90% | 68/323 (21.05%) |
| ai | 27/27 | 27/27 (100.00%) | 90% | 3/27 (11.11%) |
| gateway | 233/255 | 236/255 (92.55%) | 90% | 11/255 (4.31%) |

Other visible groups: sealed 79/96, unassigned 238/317.
Raw baseline/final: API **2,325 -> 2,311** differing fields over 1,514 steps;
gateway **528 -> 523** over 255 exchanges. No raw replay is claimed all-green.

## What was tried and preserved

- Independently reproduced strict build, format, fast tests and both replays.
  The gateway is already standalone and in-process on the actual merged branch.
- Fixed invalid governed-query ordering/refusal metadata; three gateway cases
  now pass with no new waiver.
- Fixed anonymous attribution and provider-padded finding timestamps; four
  additional claims cases now pass, with other already-failing cases improved.
- Added automatic isolated dual-host replay, health checks, hermetic settings
  and cleanup, plus an explicitly local policy audit and negative boundary tests.
- Audited every framework waiver: four native documentation exchanges, four
  readiness-source-description exchanges and one safer CORS exchange.
  Even the documentation+CORS subset is **5/17**, already above 25%.
- Did not recreate CDN/framework markup, permissive CORS, dummy ID consumption,
  missing durability, canned tool facts or numerical equivalence waivers.
  No comparison, threshold, existing test or register was weakened.

The unchanged historical strict diagnostic additionally rejects three existing
HTML registrations by treating digits in markup as numeric figures, yielding
14/17 framework. The W3 local audit reports the registered-document treatment
used by the W2 conductor separately and never extends it to numeric JSON.

## Remaining substantive clusters

| Group | Cases | Fields | Remaining work |
|---|---:|---:|---|
| gateway | 19 | 49 | Two person-lane refusals (16 fields); two governed catalogues (17); fifteen genuine identity cases (16) |
| reads_calc | 8 | 148 | Six bounded/unavailable status cases; two money-string/run-ID cases |
| claims_artifacts_rules | 21 | 100 | Later IDs, four status envelopes, zero-year filter metadata |
| drafts_runs | 10 | 19 | Seven ID/durability cases, one state-filter status, two stored-program cases |
| ai | 0 | 0 | None under current free-text policy |

## Human decision required

Resolve the framework waiver accounting/cap policy for native documentation,
safer CORS and truthful readiness. Either explicitly approve their treatment
outside the cap, define an appropriate framework-specific limit, or retain
the stop. This session changes none of those rules.

Separately preserve the existing owner queue: person-lane privacy versus
recorded valid authorization, genuine ID allocation history, native money
scale and long-text storage, stored batch-program/base-year semantics,
M-01 and first-program pricing, stronger source versions, cross-replica
idempotency/recovery, and trusted deployed ingress.

Evidence and exact reproduction commands are in
`GATEWAY-CONVERGENCE-REPORT.md`. Final raw reports and case/path/category boards
are under `artifacts/w3-final-replay`; fast TRX evidence is under
`artifacts/w3-final-fast`. All changes are local and inside `dotnet`.
