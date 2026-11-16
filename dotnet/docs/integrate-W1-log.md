# W1 integration repair log

## Preflight

Read the complete integration prompt and all four merged session status records
and running logs. The worktree is clean on `dotnet/integration`.
Ownership is limited to `dotnet/`, `contract/` and `parity/`; no live system
access is authorized. Domain certification and all comparison thresholds stay
unchanged.

## Stage 1

The merged central package file declares Microsoft.Data.SqlClient 7.1.2 twice,
once in Persistence and once in Sources/Auth/AI. Removed only the redundant
Sources/Auth/AI declaration; both projects continue using Persistence's identical
MIT package/version. No package was added or upgraded.

The supplied formatter diagnostics also identify missing references/imports in
parity tests after adapter extraction. Rebuilding the actual integrated solution
will identify the complete dependency failures before making further changes.

The actual integrated build passes after that one removal: SDK 10.0.404,
zero warnings/errors, 57.38 seconds. A full `-t:Rebuild` also passes with zero
warnings/errors in 36.76 seconds. Both format verification invocations pass.
The reported CS1503/CS0246 diagnostics do not recur on the clean rebuild;
there is no reason to change imports or project references speculatively.
The approved oracle is CPython 3.12.13 and resolves the integration backend.

The initial complete fast suite passes 788 tests without failures/skips
(Domain 18, Architecture 16, API 46, Parity 61, Sources 108, Auth 147,
AI 167, Persistence 125). Reviewing individual TRX durations found five
Persistence methods above 20 seconds: malformed seed values 25.50s,
operational reset 29.20s, reset insert failure 26.34s, publication rollback
at employee-period insertion 23.50s, and registration/seed integration 23.56s.
Added method-level heavy traits to these five methods (seven cases including
the existing three-case rollback theory). All assertions and test inputs are
unchanged; these tests remain available for the wave-end heavy gate.
Removed the temporary machine-specific TRX reports after recording aggregate
evidence.

## Stage 2

The first replay startup probe timed out before the host was ready. Its helper
was stopped in `finally`; a process inventory confirmed no worktree host
remained. This is a readiness-probe timeout, not a product change. The next
attempt will tolerate only transient connection/timeout exceptions while
waiting for readiness.

## Final gate evidence

Final `dotnet build TaxCredit.slnx -warnaserror`: zero warnings/errors, 8.90s.
`dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
`dotnet test TaxCredit.slnx --no-build --filter 'Category!=heavy'`:
781 passed, zero failures/skips (Domain 18, Architecture 16, API 46,
Parity 61, Sources 108, Auth 147, AI 167, Persistence 118).
The seven newly classified heavy cases also passed unchanged in a separate
focused run (12s). The difference from 788 to 781 is scheduling only.
The previously classified full heavy corpus is reserved for the wave-end gate.
Registry generation `--check`, five Python replay/launch helper tests, and
`git diff --check` pass.

The successful replay uses the actual inventory-marker launch configuration:
`TCC_CONTRACT_DIR` set, `TCC_CONTRACT_HOOKS` absent, `dotnet run --no-build
--no-launch-profile`, pinned SDK 10, dynamically selected loopback port.
Health and empty-object reset both return 200 before comparison starts.
The unchanged semantic replay produces all 12 fresh scenario reports and
compares all 1,769 exchanges. The payload-free board is
`dotnet/docs/replay-integrate-W1-board.json`; ignored diagnostic reports are
under `dotnet/artifacts/integrate-W1/replay/`.

Board results exactly match the merged skeleton baseline: framework 29/39
(74.36%), controls 4/4, reads 82/520, claims/artifacts/rules 58/397,
drafts/runs 54/398, AI 3/31, sealed workspace 56/125, gateway 0/255.
No waivers are applied. Business/gateway groups remain red because their
HTTP handlers are deferred, not because integration changed behavior.
The task's replay acceptance is board-only; no full HTTP equivalence is claimed.
All replay processes are stopped and a worktree-specific process inventory
confirms no host remains.

No calculated figure, stored value, authorization result, route, port,
comparison or threshold changed. The session improvements register is empty
because the repair introduces no deliberate Python behavior difference.
No package addition/upgrade, external service access, private fixture access,
push, remote change or edit outside the permitted paths occurred.
Existing owner-review items remain in the merged session records: M-01,
first-program credit math, strict leap-day fiscal shifts, deployed finding
audit provisioning and unmeasured live platform behavior.
