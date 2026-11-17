# W4 integrated-branch repair log

## Preflight

- Read the complete conductor task, W4 integration/deployment status and logs,
  merge log, host architecture and current replay-policy projection. Starting
  branch `dotnet/integration`, clean revision `7ecce3a`.
- Ownership remains `dotnet`, `contract` and `parity`; no remote, live system,
  deployment or product-Python changes are needed or authorized.
- Oracle verified as CPython **3.12.13**, importing this worktree's backend.
  Running .NET commands from `dotnet` selects SDK **10.0.404**.
- The first `--no-build` heavy invocation aborted before discovery with
  `DotnetTestHostManager.GetTestHostPath` / `NullReferenceException` against
  stale build outputs. Rebuilding the solution succeeded with zero warnings
  and errors. The rebuilt heavy run retains per-test TRX evidence under
  `dotnet/artifacts/integrate-W4-heavy-built`.
- The reported conductor failure concerns one HTTP heavy test, not a licensed
  dependency or a replay threshold. No comparisons, assertions, thresholds,
  behavior or improvement registers have been changed.

## Stage 1: rebuilt heavy gate

- Rebuilt with `dotnet build TaxCredit.slnx -warnaserror --verbosity quiet`.
  The subsequent unchanged full command
  `dotnet test TaxCredit.slnx --no-build --no-restore --filter Category=heavy`
  passed **141/141**, zero failures and skips, in one invocation: API **38**,
  persistence **11**, source **1**, parity **91**. API duration **8m 5s**.
- The original conductor's one-case HTTP failure did **not** recur. Its
  supplied stack excerpt does not identify a case or establish its cause.
  Do not attribute that original failure to the separately observed stale
  test-host outputs, or invent a production fix from a passing rerun.
- Retained the original test scheduling, HTTP timeouts, assertions, comparison
  code, certified values, package pins and all runtime source. There is no
  behavior change or new replay waiver.

## Stage 2: complete fast/build/format checks

- The whole fast suite, run after the green heavy invocation, passed
  **1,559/1,559**, zero failures and skips, across **11** assemblies.
- `dotnet format TaxCredit.slnx --verify-no-changes --no-restore
  --verbosity quiet`: exit **0**.
- A second build for the existing isolated replay launcher,
  `dotnet build TaxCredit.slnx -c Release -warnaserror --verbosity quiet`,
  passed with **zero warnings/errors**. Debug executable prerequisites from
  the initial build remain available to the existing executable tests.
- Full API/gateway semantic replay ran through the unchanged
  `spikes/shadow/hermetic.py --baseline` launcher: direct Release DLLs,
  scrubbed child environments, loopback-only listeners, distinct synthetic
  SQLite/artifact stores and the public scenario-specific reset/auth setup.

## Replay and finish

- Both replay hosts completed: API **1,514** steps / **2,311** raw differing
  fields / **9** scenarios; gateway **255** steps / **523** raw fields /
  **3** scenarios. The replay subprocesses return **1** for completed
  comparisons with differences; their enclosing launcher correctly exits **0**.
- Applied the existing current-policy scorer without editing it, its route
  ownership, registers or recorded exchanges. All required thresholds pass:

  | Group | Passed / HTTP cases | Percent | Required |
  | --- | --- | --- | --- |
  | framework | 17 / 17 | 100.00 | 90 |
  | reads_calc | 406 / 414 | 98.07 | 95 |
  | claims_artifacts_rules | 295 / 316 | 93.35 | 90 |
  | drafts_runs | 312 / 323 | 96.59 | 90 |
  | ai | 27 / 27 | 100.00 | 90 |
  | gateway | 236 / 255 | 92.55 | 90 |

- Every current waiver cap also passes (including the existing sub-40-case
  exemption); all four control steps pass. Fresh per-group scores exactly
  equal the merged W4 evidence. **637 inherited unresolved fields** remain
  across scored and separately reported groups; threshold success is not
  zero-difference parity or cutover readiness.
- Generated `integrate-W4-gates.json` directly from all **22** heavy/fast TRX
  files and both raw replay reports. It records counts, safe relative evidence
  paths, raw-report hashes and current policy, never payloads or credentials.
- This repair requires **no source/test/configuration/package changes** and
  no new improvement registration. A full rebuild and fresh passing evidence
  are sufficient for this session; the incomplete original HTTP stack does
  not justify guessing a code change or relaxing a deadline.
- The finish status's `head` names tested source revision `7ecce3a`; the
  subsequent local commit contains only this log, aggregate gate evidence
  and finish status. No push, remote change or live system contact occurred.
