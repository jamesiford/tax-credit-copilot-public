# Required hard stop: AI replay cannot be completed within this assignment

The latest conductor gate reports **13/27 AI cases passing (48.1%)**,
with **5/27 waiver-dependent cases (18.5%)**. Replay is not accepted.
This is a blocked delivery, not a successful implementation claim.

## What happened

The task permits only AI-owned source folders and documentation, forbids
copying sibling calculations, and explicitly prohibits code written solely
to reproduce validation English/context, byte-level headers or Python bugs.
The branch still contains no ReadsCalc or ClaimsDrafts application features.
The canonical services required by `ICapabilityReadBridge` and
`IAiPageCollaborator` therefore remain unavailable on the ordinary host.

Hard stop 1 applies: completing those missing sibling implementations would
require changes outside the owned paths. Implementing competing calculations
inside AI or changing the fixed acceptance policy is not an authorized
alternative. This HALT file intentionally means `no_halt` cannot be claimed.

## What was tried and verified

The implementation already uses callable W1 ports for local reads, exposes
narrow sibling contracts, and exercises realistic injected collaborators.
Earlier follow-ups corrected a real analyzer defect and removed overbroad
waivers; neither action supplied the missing production services.

On this follow-up, all current AI replay differences were inspected against
the task policy and current feature availability. No new owned behavior defect
was identified that could resolve the gate without violating those constraints.
The improvements register and product behavior were not changed.

The same mechanical checks were rerun: `dotnet build -warnaserror`,
`dotnet format --verify-no-changes`, and
`dotnet test --filter 'Category!=heavy'` all pass. There are 1,025 passing
tests, no failures or skips, and zero build warnings/errors.

The unchanged semantic replay was rerun on CPython 3.12.13 through a fresh,
health-checked ordinary local host, covering all twelve scenarios and all
1,769 exchanges. It reports 9,472 raw field differences, six tolerated
differences, and **8/27 raw passing AI cases** under the exact four-operation
selection. The existing wrapper includes four additional method/slash cases
and reports 11/31; it does not apply improvements and is not the conductor's
adjusted percentage. The owned scenario remains 36 exchanges and 192
differences. Diagnostics are under the ignored
`dotnet\artifacts\ai-hard-stop-replay` directory. The host was stopped.

## Decisions and integration required

1. Integrate the canonical ReadsCalc portfolio/eligibility projections and
   portfolio/unit/employee page services, then bind the existing AI seams.
   The three capability failures are `capabilities.book-rank`,
   `capabilities.client-eligibility`, and `agent.capabilities-book-rank`.
   Missing page projections must not be hidden by privacy or error waivers.
2. Resolve `DEC-AI-1`: ten error/header-only cases require differences that
   the task explicitly excludes from reproduction. The 25% cap permits six
   waived cases out of 27. Even if every other case were fixed, four failures
   would remain, limiting acceptance to 23/27 (85.2%), below 95%.
   This session did not change the comparator, thresholds or policy.
3. Resolve `DEC-AI-2`: confirm the canonical offline-chat and client-summary
   behavior instead of the recorded unrelated demonstration and SQL-binding
   defect. The two retained defect entries remain narrowly event-scoped.

The conductor's five waiver-dependent cases include matches from the W1
`sources_auth_ai` register as well as this feature's register. This feature's
two retained entries alone can touch at most three AI cases; that scope bound
is not an adjusted pass claim. Other sessions' registers were not modified.

Resume after the missing canonical services or an explicit policy/ownership
decision is supplied. No live external system, push, remote change, private
data, unowned edit, canned response or changed calculated figure was used.
