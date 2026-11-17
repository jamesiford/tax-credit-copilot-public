# Wave W1b report (Host composition: bind the real adapters into the API and Worker hosts, and repair what wave 2's first attempt found)

Written by the conductor at 2026-11-16T06:02:34+00:00. Session summaries are the sessions' own words from STATUS.json; gate results are the conductor's.

## composition: ok (attempts 1, branch `dotnet/w1b-composition`, head `ede15fd`)

Shared production API/Worker composition, pre-build feature discovery, real trust/reset/source/byte controls and durable transactional execution are implemented.
Persistence repairs cover selected years, durable override order and unbounded draft paging.
Build/format pass; 712 fast tests, seven API heavy tests and three CPython launch tests pass.
All twelve semantic scenarios / 1769 exchanges completed with zero waivers.
Framework raw scores are 26/39 wrapper and 8/19 exact membership; real readiness differences remain visible in this board-only wave.
Business/gateway handlers and live native/private-reference certification remain deferred.
The historical 781-test claim sums to 681 in its listed counts; no baseline tests were deleted.
The head identifies the verified implementation commit; the following local commit contains reports/status.

- gate no_halt: PASS
- gate commits_present: PASS
- gate clean_tree: PASS
- gate not_pushed: PASS
- gate owned_paths: PASS
- gate status_json: PASS
- gate report_present: PASS
- gate dotnet_build: PASS
- gate dotnet_format: PASS
- gate tests_fast: PASS
- gate replay: PASS

**deviations**
- {"id": "DEV-1", "what": "Readiness exposes real source-account observations rather than captured skipped/scan-counter placeholders.", "why": "The task requires real settled observations, not fabricated parity counters. Raw replay failures remain visible; no waiver or old 50-percent threshold pass is claimed.", "decision_needed": true}
- {"id": "DEV-2", "what": "The measured initial fast baseline is 681 by the historical report's own enumerated assembly counts, not its stated 781.", "why": "The final measured 712 equals those counts plus 20 API and 11 Persistence cases. Existing tests were not deleted.", "decision_needed": false}

**findings**
- Seed loading consumes no runtime UUID calls; the live sequence must resume after synthetic seed high-water marks, independently of secrets.
- Assigning an AsyncLocal principal inside awaited access validation does not reliably propagate into endpoints; explicit middleware push/restore is required.
- Python F-14 valid-request exceptions are intentionally retained by supplied policy; F-15 draft-list reads need no invented actor.
- Lost historical override order at identical timestamps cannot be recovered; deterministic backfill is not proof of intent.
- P1 readiness now reports observed source state, reducing exact framework raw score from 11/19 to 8/19; the wave is board-only with zero waivers.
- M-01 ingestion precedence, first-program credit math, contextual leap fiscal handling, zero-worksite projection and native monetary AVG remain figure-sensitive boundaries.

**open_questions**
- Which stable readiness observation shape should replace the recorded placeholder fields before applying the previous framework threshold?
- What lease duration and renewal boundary are required for measured long native calculations?

**needs_human**
- {"item": "Readiness contract and historical baseline bookkeeping", "why": "Review the truthful observation wire shape and reconcile the historical 781-versus-681 arithmetic; neither was hidden by waiver or altered tests."}
- {"item": "Deployed schema and historical override decisions", "why": "Provision the documented forward-only native additions, verify actual transaction/grant behavior, and review equal-timestamp legacy choices before enabling writers."}
- {"item": "Figure-sensitive inherited behavior", "why": "Owner decisions are needed for M-01 ingestion precedence, first-program credit math, strict leap-window context, zero-worksite SQL/projector differences and native monetary AVG."}
- {"item": "Native operational and source freshness certification", "why": "No live service was authorized. Cross-replica publication, pooling/token refresh and count/max-preserving edits are not certified by local/fake tests."}
- {"item": "Long synchronous work and production AI", "why": "Lease expiry rolls back rather than accepting stale ownership; long runs need measured sizing/renewal design. Foundry invocation needs an installed factory and separate approval."}
- {"item": "Private reference and next-wave business handlers", "why": "No private payroll was loaded; certified constants remain untouched. Business HTTP/gateway implementations are outside composition and still return stubs."}

**reports**
- dotnet/docs/COMPOSITION-REPORT.md
- dotnet/docs/HOST-ARCHITECTURE.md
- dotnet/docs/COMPOSITION-SCHEMA-PROVISIONING.md
- dotnet/docs/composition-log.md
- dotnet/docs/improvements/composition.json
- dotnet/docs/replay-composition-board.json
- dotnet/docs/replay-composition-framework.json

## Replay board `W1b-composition.board`
```
{
 "_unassigned": {
  "exchanges": 319,
  "failing_cases": 81,
  "waived_cases": 0,
  "waived_percent": 0.0,
  "pass_percent": 74.6
 },
 "ai": {
  "exchanges": 27,
  "failing_cases": 22,
  "waived_cases": 5,
  "waived_percent": 18.5,
  "pass_percent": 18.5
 },
 "claims_artifacts_rules": {
  "exchanges": 316,
  "failing_cases": 310,
  "waived_cases": 6,
  "waived_percent": 1.9,
  "pass_percent": 1.9
 },
 "drafts_runs": {
  "exchanges": 323,
  "failing_cases": 265,
  "waived_cases": 58,
  "waived_percent": 18.0,
  "pass_percent": 18.0
 },
 "framework": {
  "exchanges": 19,
  "failing_cases": 7,
  "waived_cases": 4,
  "waived_percent": 21.1,
  "pass_percent": 63.2
 },
 "gateway": {
  "exchanges": 251,
  "failing_cases": 251,
  "waived_cases": 0,
  "waived_percent": 0.0,
  "pass_percent": 0.0
 },
 "reads_calc": {
  "exchanges": 414,
  "failing_cases": 354,
  "waived_cases": 60,
  "waived_percent": 14.5,
  "pass_percent": 14.5
 },
 "workspace_sealed": {
  "exchanges": 96,
  "failing_cases": 60,
  "waived_cases": 3,
  "waived_percent": 3.1,
  "pass_percent": 37.5
 }
}
```

**Improvements register: failures covered (for the owner to review)**
- IMP-composition-1 (defect_fix): 18 failing field(s)
- IMP-composition-2 (defect_fix): 192 failing field(s)
- IMP-persistence-1 (defect_fix): 92 failing field(s)
- IMP-skeleton-1 (defect_fix): 12 failing field(s)
- IMP-skeleton-2 (defect_fix): 4 failing field(s)
- IMP-skeleton-3 (defect_fix): 4 failing field(s)
- IMP-skeleton-4 (defect_fix): 111 failing field(s)
- IMP-sources_auth_ai-2 (defect_fix): 38 failing field(s)
- IMP-sources_auth_ai-3 (defect_fix): 212 failing field(s)
- IMP-sources_auth_ai-5 (defect_fix): 17 failing field(s)

## Replay board `W1b-integrate-W1b.board`
```
{
 "_unassigned": {
  "exchanges": 319,
  "failing_cases": 81,
  "waived_cases": 0,
  "waived_percent": 0.0,
  "pass_percent": 74.6
 },
 "ai": {
  "exchanges": 27,
  "failing_cases": 22,
  "waived_cases": 5,
  "waived_percent": 18.5,
  "pass_percent": 18.5
 },
 "claims_artifacts_rules": {
  "exchanges": 316,
  "failing_cases": 310,
  "waived_cases": 6,
  "waived_percent": 1.9,
  "pass_percent": 1.9
 },
 "drafts_runs": {
  "exchanges": 323,
  "failing_cases": 265,
  "waived_cases": 58,
  "waived_percent": 18.0,
  "pass_percent": 18.0
 },
 "framework": {
  "exchanges": 19,
  "failing_cases": 7,
  "waived_cases": 4,
  "waived_percent": 21.1,
  "pass_percent": 63.2
 },
 "gateway": {
  "exchanges": 251,
  "failing_cases": 251,
  "waived_cases": 0,
  "waived_percent": 0.0,
  "pass_percent": 0.0
 },
 "reads_calc": {
  "exchanges": 414,
  "failing_cases": 354,
  "waived_cases": 60,
  "waived_percent": 14.5,
  "pass_percent": 14.5
 },
 "workspace_sealed": {
  "exchanges": 96,
  "failing_cases": 60,
  "waived_cases": 3,
  "waived_percent": 3.1,
  "pass_percent": 37.5
 }
}
```

**Improvements register: failures covered (for the owner to review)**
- IMP-composition-1 (defect_fix): 18 failing field(s)
- IMP-composition-2 (defect_fix): 192 failing field(s)
- IMP-persistence-1 (defect_fix): 92 failing field(s)
- IMP-skeleton-1 (defect_fix): 12 failing field(s)
- IMP-skeleton-2 (defect_fix): 4 failing field(s)
- IMP-skeleton-3 (defect_fix): 4 failing field(s)
- IMP-skeleton-4 (defect_fix): 111 failing field(s)
- IMP-sources_auth_ai-2 (defect_fix): 38 failing field(s)
- IMP-sources_auth_ai-3 (defect_fix): 212 failing field(s)
- IMP-sources_auth_ai-5 (defect_fix): 17 failing field(s)
