# ADR 0004: Test and assertion libraries, and architecture tests

Status: accepted (spike). Date: 2026-11-14.

## Licences (verified from the repositories on 2026-11-14)

| Library | Licence | Decision |
|---|---|---|
| xUnit v2 (`xunit` 2.9.3) | Apache-2.0 (".NET Foundation and Contributors") | **Use.** xUnit v3 is the successor; adopt when the tooling (VS Test Platform runner, analyzers) is settled on our SDK. |
| FluentAssertions 8 | Xceed Community License Agreement (free for non-commercial use, paid for commercial) | **Do not use.** |
| Shouldly | BSD 3-Clause | Acceptable alternative; not needed. |
| NUnit | MIT | Not needed. |
| NetArchTest.Rules | MIT, but last push 2024-07 | Not used: the rules we need are a few reflection and project-file checks. |
| ArchUnitNET | Apache-2.0, active | Candidate if the rule set grows beyond what `LayeringTests` expresses. |

## Decision

- xUnit assertions only (`Assert.*`); no assertion library. The parity harness needs bespoke bit-level comparers
  anyway, and the Python vectors are the real oracle.
- Architecture rules are plain reflection plus project-file parsing (`TaxCredit.Architecture.Tests`), so there is no
  dependency to license-check or keep patched. Each rule is paired with a mutation self-test.
- Parity tests compare doubles with `BitConverter.DoubleToInt64Bits` (`PyFloat.SameBits`). The only relaxation is that all
  NaNs compare equal, because .NET's `double.NaN` has the sign bit set and Python cannot observe the difference (flagged
  in `findings.md` as T-12 for review).
