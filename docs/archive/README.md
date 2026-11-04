# Archive

Superseded briefs, reports and dated evidence. They are kept as the record of what was done and measured at the time; **none of
it is current**. Each file was moved here with `git mv`, so its history follows it. What replaced it is named below.

| Archived | What it was | Where the current answer is |
| --- | --- | --- |
| [m365-channel/STATUS.md](m365-channel/STATUS.md) | The first run's work-package table (CH-01 to CH-18, AI-01 to AI-08) | [REMEDIATION-STATUS.md](../m365-channel/REMEDIATION-STATUS.md) for the remediation run, [MASTER-STATUS.md](../m365-channel/MASTER-STATUS.md) for the master run, [FINAL-STATE.md](../m365-channel/FINAL-STATE.md) for what is deployed |
| [design/UI-REVAMP-BRIEF.md](design/UI-REVAMP-BRIEF.md) | The brief for the modern-theme revamp | [DESIGN-SYSTEM.md](../design/DESIGN-SYSTEM.md) |
| [design/REVAMP-REPORT.md](design/REVAMP-REPORT.md) | The report on the earlier revamp rounds | [DESIGN-SYSTEM.md](../design/DESIGN-SYSTEM.md), [UI-STATUS.md](../design/UI-STATUS.md) |
| [design/UI-REVAMP-RESULT.md](design/UI-REVAMP-RESULT.md) | The revamp's result: what changed, what did not, the before and after numbers | [UI-STATUS.md](../design/UI-STATUS.md) |
| [evidence/live-final-2026-11-03.md](evidence/live-final-2026-11-03.md) | Live verification after the CH-17 redeploy (agent version 20) | [live-remediation-2026-11-04.md](../m365-channel/evidence/live-remediation-2026-11-04.md) for the latest live run |
| [evidence/live-smoke-2026-11-03.md](evidence/live-smoke-2026-11-03.md) | The gateway's live smoke run | the same smoke script, `scripts/channel-smoke.ps1`, re-run against the current deployment |
| [evidence/model-access-2026-11-03.md](evidence/model-access-2026-11-03.md) | The model-access investigation from the hosted agent (D-101) | [DECISIONS.md](../m365-channel/DECISIONS.md) D-101 and D-127 |

Two UI documents stay where they were, because code reads or cites them: `design/ASK-EVIDENCE-CONTRACT.md` (backend tests and the
evidence validator), and `design/DESIGN-SYSTEM.md`, `design/UI-DECISIONS.md` and `design/UI-STATUS.md` (named in frontend sources
and tools, which this run does not touch). `m365-channel/evidence/publish-whatif.txt` stays because a test reads it.
