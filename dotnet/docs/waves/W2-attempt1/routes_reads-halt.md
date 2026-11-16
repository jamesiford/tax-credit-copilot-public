# ReadsCalc replay policy hard stop

**Hard-stop 3: repeated attempts cannot satisfy the replay gate and the fixed
behavior requirements simultaneously.** This is a new, numerical/policy stop,
not the earlier, disproven claim that feature composition required shared edits.
Product code remains at `c253ade`; the composition repairs and all 741 fast
tests remain valid.

Fresh final checks: whole strict build and formatter passed; all 741 fast
tests passed. All twelve scenarios completed again with 1,769 exchanges,
6,765 raw failing fields, 188/414 exact owned cases and 38/40 P2 cases matching.
Replay exited 1. Outputs are local ignored `dotnet/artifacts/reads-06*`; the
report preserves these figures independently. The owned API helper is stopped.

## What was attempted

1. Implemented the 29 operations and corrected root-captured source/fiscal
   services, duplicate explicit routes, provider validation and attribution
   inside the owned feature. These were real defects and are fixed.
2. Executed complete semantic scenarios with explicit profile/auth setup.
   Correctly selected P2 matches 38/40 owned cases; the exceptions are honest
   population metadata and free 404 wording. Completed the heavy token/lifecycle
   and calculation comparisons. Did not weaken recorded values or tests.
3. Classified all 82 unwaived conductor cases and independently reproduced
   incorrect default-profile and auth setup on the normal host. Repeated the
   complete gates and replay after reporting explicit `needs_human` decisions.
   The next conductor run returns the identical case partition and score.

The latest conductor reports 332/414 after registered differences and
207/414 waived (50%, against a 25% cap). Its remaining cases are 37 P2 setup,
two auth setup, 30 shared identity/page-bound refusals, eleven honest-count
metadata differences and two missing sibling-write envelopes. No unexplained
owned-handler defect was found in that partition.

## Decisions required before another implementation attempt

- **Counts:** preserve Stage 2's explicit page-independent totals and authorize
  corresponding recording expectations, or explicitly supersede Stage 2 and
  authorize Python's page-dependent metadata. For example, P1 limit 1 records
  1/1 but the stored populations are 21/10; P2 limit 3 records 3/3 but the
  populations are 26/13. The existing instruction forbids numerical waivers.
- **Errors and cap:** settle Tier C's free JSON-detail wording and the explicit
  ban on Pydantic/framework emulation versus the 25% register cap. The conductor
  counts 50% waived. Do not silently relax the cap or implement forbidden
  framework-emulation code in this feature.
- **Replay setup:** select the scenario profile and auth settings explicitly.
  The conductor's P2 scope reports CSV; the correctly selected profile reports
  lakehouse and four clients. Restricted reads return 200 locally and 403 after
  explicit auth setup with the same in-memory token. Product code must not
  infer profile or authentication policy from an account or token.
- **Shared bounds and dependencies:** decide the existing positive storage-ID
  and bounded-page contract, and integrate sibling writes before requiring
  their dependent run identities/overrides. ReadsCalc cannot fake those writes.

`status/routes_reads.json` records these decisions under `needs_human` and
keeps `replay` false. This HALT necessarily makes `no_halt` false; hiding it
would contradict the task's mandatory hard-stop path. No code, register,
recording, comparison, test, threshold or external worktree was changed to
conceal a failure. See `ROUTES-READS-REPORT.md` for exact current verification.
