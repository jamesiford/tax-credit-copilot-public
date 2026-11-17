# W1b composition log

## Preflight

Read the task, integrated host/adapter/domain/platform reports, W1 integration
evidence, contract policy/control/freeze/auth/seed definitions and archived W2
reports without merging them. No live system access is authorized or used.
The branch is `dotnet/w1b-composition` and the initial worktree is clean.

Baseline from `dotnet`, SDK 10.0.404: build passes with zero warnings/errors.
The historical integration report claims 781 non-heavy tests across eight assemblies (18 Domain, 16 architecture,
46 API, 61 parity, 108 Sources, 147 Auth, 167 AI, 118 Persistence).
Those listed assembly counts actually sum to 681, not 781. The current measured
gate, before the final additional cases, is 711 passing tests: 66 API and 128
Persistence, with the other six counts unchanged. No baseline test was removed.
Existing persistent CPython 3.12 testhost settings remain unchanged.

The shared boundary will live in ServiceDefaults (outward adapter composition)
and Application Hosting/Ports (framework-independent execution contracts).
API and Worker will not reference each other. Feature discovery must execute
before provider construction, with endpoint mapping remaining post-build.
Persistence uses one database for Gold, manifests, claims and queue.

Durable override ordering will use a transactionally updated persisted counter,
not GUID or timestamp order. Local existing rows can be upgraded deterministically,
but their lost historical tie order cannot be recovered; deployed provisioning
must be explicit and is not certified by local tests.

## Composition and persistence checks

C1 discovery runs before Build from the API/Application assemblies and explicitly
configured feature assemblies. A discovered test module registers its own
collaborator; its real endpoint replaces the matching stub.

C2 selected years round-trip through real SQLite reopen. The override counter is
updated transactionally with each append; reverse IDs, identical timestamps,
independent/concurrent connections, clear and upgrade/reopen cases pass. Native
SQL bindings retain UTC timestamps, public IDs, tenant parameters and write order.
Draft paging counts before paging, uses BigInteger HTTP validation and Int64 SQL
offsets, including COUNT_BIG on the native provider.

Both executables now use the same outward ServiceDefaults registration. The
non-HTTP executor and publication contracts live in Application Hosting/Ports.
Auth uses real RS256 verification, explicit principal push/restore after awaits,
person writer policy and caller-keyed limiting. Seed reset restores persisted
state, source generation, limits, budgets and artifact generations.

Verified: 124 fast persistence tests before publication cases were added;
four new publication cases then passed (recovery without recalculation,
independent publishers, rollback on cancellation and lease refusal).
Real drain and a real finite Worker process publish the P1 manifest, Gold and
claims, then survive reopening. Their expected 107/77/72 figures come from the
unchanged P1 manifest, not the unrelated certified TY2023 fixture.
P2 staged catalogue, footprint, authored fiscal window and CSV restoration pass
in a heavy integration test. No live service was contacted.

Important integration trap: loading a seed consumes no runtime UUID calls, but
Python created its seed with those calls. Restarting at one collided with existing
claim identities. Reset now resumes after the verified seed's synthetic UUID
high-water mark (P1 three, P2 twenty-six), independently of the secret counter.
The first heavy checks exposed incorrect test assumptions about P1 figures and
which synthetic client has a July fiscal year; assertions now read the actual
seed contract. API socket startup needed bounded timeout retries.

## Final integration evidence

The shared root now also owns `IHostStatus`, so direct Worker/shared provider
validation resolves framework handlers without an API-only registration.
Native SQL/Blob/group-policy selection resolves real adapters without opening a
live connection; the group transport in that check is fake.

The retry fixture initially contained an unintended explicit-interface
`NotImplementedException` stub (an automatic formatting/code-fix artifact while
its return type was being corrected). A temporary in-memory failure diagnostic
identified it; the stub and diagnostic were removed. The actual source-outage
backoff and cancellation/refunded-attempt behavior both pass.

Final measured fast gate: **712 passed, zero failed/skipped**, across Domain18,
Architecture16, API66, Parity61, Sources108, Auth147, AI167, Persistence129.
All **seven** API heavy cases pass, including the actual API socket, finite
Worker process and P2 staged source. Original CPython launch-bridge tests: **3
passed**. Solution warning-as-error build and full format verification pass.
No new package or licence review was needed.

Full semantic replay used the ordinary `dotnet run --no-launch-profile` API,
with a valid inventory marker and **no explicit hook flag or test assembly**.
All twelve scenarios / **1,769 exchanges** completed against isolated local
stores. The helper stopped its own API process in `finally`.
Fresh absolute raw reports were generated under ignored
`dotnet\artifacts\composition-replay-final\raw`; payload-free aggregate and
framework-case reports are checked in.

Wrapper framework: **26/39 (66.67%)**, versus 29/39 (74.36%).
Exact method/template framework membership: **8/19 (42.11%)**, versus the
authoritative baseline 11/19 (57.9%). This is a new exact-membership calculation
over the complete replay, not a new invocation of the external conductor.
Three added P1 readiness differences reflect real source observations replacing
recorded skipped/counter placeholders. No waivers, changed thresholds, invented
readiness counters or changed certified constants. The wave's gate is board-only;
the old 50% authoritative framework threshold is not claimed.
