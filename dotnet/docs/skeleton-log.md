# W1 skeleton session log

## Resume and scope

The initial stop commit was `6eb8305`, from baseline `b8e17f4`. The conductor
explicitly resumed the session to remove the halt and deliver the required
reports/status. That instruction authorizes these mandatory `dotnet/docs`
outputs; no unrelated owned-path exception was taken. The halt report is removed.
Stage 4's `improvements/W1-skeleton.json` is the primary register; the fixed-rule
filename `improvements/skeleton.json` is an identical compatibility copy,
checked for drift by a test.

## Preflight

Read the contract README, report (especially sections 4-6), findings,
normalisation/auth contract, controls/replay/inventory, domain/spike reports,
the .NET ADRs and existing host/messaging in the specified order. Checked the
coverage/scenarios, platform risks and existing browser/BFF origin configuration.
The prepared infrastructure and API-test project shells and skeleton package
section exist. Used .NET SDK 10.0.404 and the supplied CPython 3.12.13 oracle.

Baseline build with warnings as errors and format verification passed.
Before classification, the fast test selection included the entire parity
corpus: Domain 18 passed, Architecture 13 passed, Parity 152 passed.
Parity ran from 14:20:42 to 14:39:55: **19m12s**.
The oracle was explicitly configured for baseline; subsequent fast tests prove
the persisted runsettings work without an external `TCC_PYTHON`.

## Implementation decisions

- Generate a method-level registry and captured schema resource without Python
  product imports. Partition all API, HEAD documentation and gateway operations.
  Include all eleven actual workspace routes despite the prompt's count of ten.
- Reflect endpoint groups, then fill only unclaimed operations with JSON 501.
  Keep the existing in-house mediator and pure Domain unchanged.
- Use STJ transport DTOs, invariant scale-preserving money strings and portable
  JSON error families. No custom byte/order/number-lexeme parity writer.
- Validate captured parameters/body schemas before dispatch. Keep access refusal
  ahead of emitting validation details on protected operations.
- Use explicit standard CORS and native routing defaults; do not reproduce
  reflection, 307, case-sensitive-path or documentation-CDN artifacts.
- Add startup-only, host-local, serialized contract seams. Ephemeral RSA minting
  and public key are available to the auth session; real seed/reset/drain work
  is a replaceable port, not implemented storage.
- Fail closed outside explicit local/hermetic bypass until real auth is bound.
  Real data-dependent readiness remains unavailable rather than fabricated.
- Provide sealed missing-input responses without importing reference modules.
  Record F-6/F-4/F-3/F-1 corrections; no calculated/stored figures change.
- Add `Microsoft.AspNetCore.TestHost` **10.0.0** only in the skeleton package
  section. Its NuGet package license is **MIT**, verified before adding it:
  https://www.nuget.org/packages/Microsoft.AspNetCore.TestHost/10.0.0
  No other new package or commercial mediator was introduced.
- Persist the supplied 3.12 oracle in Parity runsettings via conditional
  `VSTestSetting`; the oracle's strict CPython-version check remains intact.

## Heavy classification

Assertions are unchanged. Tagged twelve corpus-heavy classes, six fuzz methods
and four measured slow methods. Decompressed families exceed 20 MB:
engine 129.44, primitives 108.29, coverage 34.77, credit math 86.92, Gold 21.74,
pack validation 67.85, performance 32.55, proximity 37.43 and Gold payload
148.19 MB (its input is 26.41 MB).

Baseline examples: credit-math main 18m50s, capstone 16m56s, simulation fuzz
13m44s, forecast main 12m52s, Gold main 9m42s, engine fuzz 8m03s.
Additional measured slow methods include canonical main 57s and QC main 29s.
Small Domain tests stay fast. After classification, Parity is **61/61 in 6s**,
with **9.685s wall time**, without an externally configured oracle.
The full fast-solution result is recorded below after final validation.

## Replay and investigation

In-process API suite: **46/46** passed. Also ran the unchanged semantic replay
through a real Kestrel loopback socket, not only TestServer: twelve scenarios,
1,769 exchanges, framework **29/39 = 74.36%**, controls **4/4**.
All raw scenario reports exist; the checked-in board is payload-free and applies
zero waivers. Deferred groups intentionally remain red; see HOST-ARCHITECTURE.

Fixed a JSON charset mismatch, XML-comment formatting, xUnit/analyzer issues,
and an anonymous environment payload whose keys were camel-cased by the test
client. Reset profile selection uses the scenario-specific reset URL because
the unchanged replay posts an empty object. No replay comparison was loosened.
Avoided concurrent builds/tests holding copied DLLs on Windows; stopped the
socket helper before rebuilding and will stop the final helper before finish.

No live Fabric, Foundry, Entra or customer system was contacted. No private
extract, product Python, frontend, infrastructure or certified constant was
changed. No push, PR or remote modification was made.

## Final gate evidence

Whole-solution `dotnet build -warnaserror`: passed, zero warnings/errors,
26.98s. `dotnet format --verify-no-changes`: passed.
`dotnet test --no-build --filter "Category!=heavy" --logger trx`: **141 passed**,
zero failures/skips (Domain 18, Architecture 16, API 46, Parity 61), with no
external `TCC_PYTHON`. The four test-run timestamps span **8.997s**;
build + format + fast-test command wall time was **88.178s**. The prepared
infrastructure test shells correctly report no matching tests.

Generator `--check` and `git diff --check`: passed. The registry/group partition
contains **110 method/template pairs**. Final Kestrel readiness returned 200,
then all twelve semantic scenarios produced **fresh** reports and the same
framework **74.36%**, with no waivers. Both attached replay helpers were stopped.

The final relative-path replay command exposed a wrapper bug: the subprocess
changed working directory, and an existing report could mask its output-write
failure. Resolved raw output paths before launching and remove only that
scenario's prior report before each run. Two focused stdlib tests prove absolute
output and refusal of a stale report; both pass. Reran all scenarios successfully
after the fix. The board does not accept missing reports as a successful replay.

Final status records verified gates and the inherited figure-changing fix
candidates. Local implementation and finish commits include the required
trailers; no branch is pushed or remote changed.
