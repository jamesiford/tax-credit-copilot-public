# HALT: integrate-W2

Stage 4 stopping condition: the merged branch does not honestly satisfy all
five semantic replay thresholds. Integration repairs are retained, but this is
**not a successful wave gate**.

The resumed conductor failures exposed an additional real harness defect:
external replay reset every scenario to default P1 and never installed the
auth scenario's mode. Commit `9a1ffd2` fixes the actual `--reset-url` path to
prepare each declared profile/auth world before any request. A direct full
replay on one host reduces raw failing fields from 5,740 to 3,870 and exactly
reproduces the independently prepared scenario evidence below. Comparisons,
recordings and thresholds are unchanged. This resolves the setup mismatch,
not the remaining framework/drafts stopping condition.

| Group | Final | Required | Waived | Outcome |
|---|---:|---:|---:|---|
| framework | 14/19 (73.68%) | 90% | 6/19 (31.58%) | Threshold and 25% cap fail |
| reads_calc | 406/414 (98.07%) | 95% | 26/414 (6.28%) | Meets both |
| claims_artifacts_rules | 291/316 (92.09%) | 90% | 70/316 (22.15%) | Meets both |
| drafts_runs | 287/323 (88.85%) | 90% | 42/323 (13.00%) | Threshold fails |
| ai | 27/27 (100.00%) | 90% | 3/27 (11.11%) | Meets both |

These are local policy diagnostics over all twelve actual semantic replay
reports, not a claimed external conductor run. The reports contain 1,765 HTTP
exchanges plus four controls. Gateway 0/251 is deferred; sealed workspace
79/96 and unassigned 240/319 remain visible in the full report.

## What was tried

Repaired stale/ambiguous test endpoints, actual production feature composition,
scoped mediator/leases, the real 20-query validation contract, recorded paging
metadata, source-backed footprints and AI sibling reads. Restored deterministic
source state at the application's ready boundary, including four real startup
OpenTelemetry UUID allocations. Reused the initial assessment's existing
ID/clock injection rather than rewriting the sink identity. Fixed capability
read authorization, unavailable-client reads, dictionary error classification
and stream charset. Reproduced affected scenarios before the final complete
replay. Early IDs now match; remaining allocation differences are real
business/persistence work, not an unexplained startup offset.

The comparable baseline/final board, regressions, all register changes and
verification evidence are in `ROUTES-CONVERGENCE-REPORT.md` and
`integrate-W2-log.md`. The current status pins the verified external-replay
repair on top of the verified runtime fixes.
Five setup regressions plus the five existing policy/report regressions pass;
strict build, format and all 978 fast tests pass again. Direct one-host evidence
is `dotnet\artifacts\integrate-resume-external\replay.json`; its separate
`policy.json` remains an explicitly local diagnostic, not a new official
conductor board.

## Remaining blockers and required decisions

Framework has **5 failed cases / 12 fields**. Two gateway-recorded operations
expect 404 for the ordinary API's valid `/docs` and `/openapi.json`. Three native
documentation pages contain differing numeric HTML fragments, so the existing
numeric guard rejects their waiver matches. Already accepted waivers alone
exceed 25%. Accepting those three would still reach only 17/19 (89.47%) and
would further exceed the cap. The owner must resolve server ownership and the
framework-artifact policy/cap contradiction. Do not copy FastAPI pages or hide
digits to evade the guard.

Drafts has **36 failed cases / 239 fields**: 28 durable latest-run/default-program
preview cases, seven identity/base-year durability cases and one wrong-method
outcome. The owner must reconcile the recorded disconnected latest-run store
with real durable manifests and explicit default-program resolution. A real
manifest produces different `never_run`/coverage counts; those numbers cannot be
waived, invented or made stale to pass.

Reads retains **8 failed cases / 148 fields**: six unavailable/bounded-input
status envelopes and two later-ID/money-scale cases. Claims retains
**25 failed cases / 114 fields**: 16 ID cases, three attribution-only, four
status cases, one zero-year filter case and one timestamp case. Resolve the
real remaining allocation path without dummy draws or deleting audit writes;
the exact first later divergence has not been fully traced. Decide the exact
money-string scale and valid long-text/native-column contract. Keep ordinary
attribution, unavailable-envelope, year-zero filtering and timestamp defects on
the implementation backlog, not disguised in an improvements register.

Also carry forward M01's figure-affecting ingestion overrides, first-program
credit pricing, and the fact that SQL count/max-modified fingerprints are not
immutable payroll snapshots. These were deliberately not changed without an
owner decision.

## Integrity

No threshold, raw comparator, recording or certified figure was weakened.
Removed broad/inert/obsolete waivers; the 34 new entries are route/path-specific.
Three numeric HTML matches remain rejected. No dummy IDs, fabricated preview
counts, scenario-specific API behavior, live-system access, push or change
outside owned paths was used. This committed HALT is the required result when
honest convergence cannot be claimed.
