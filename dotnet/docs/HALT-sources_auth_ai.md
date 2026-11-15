# sources_auth_ai: hard stop 1

The task cannot be completed within its fixed path restrictions.

The Rules section says "You may create or modify only" the three owned
Infrastructure projects, their tests, three Application port folders, and
`dotnet/Directory.Packages.props`. It explicitly says any other change fails
the owned-path gate.

The same task requires these paths, none of which is in that list:

- `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`
- `dotnet/docs/sources_auth_ai-log.md`
- `dotnet/docs/improvements/sources_auth_ai.json`
- `dotnet/docs/status/sources_auth_ai.json`

Hard stop 1 requires ending the run when a change outside owned paths would be
needed. The report and running log make that condition unavoidable, before
implementation. The explicit hard-stop and Finish instructions are the sole
authority used to write this halt record and the status file; no general
documentation exemption has been assumed.

## Evidence and actions

- Read the complete external task description.
- Confirmed branch `dotnet/w1-sources_auth_ai`, base commit `b8e17f4`,
  and an initially clean worktree.
- Inspected the prepared project inventory and read the domain slice report,
  port map, platform risks, API authentication contract, and normalisation.
- Confirmed no existing session halt/status files and no remote tracking
  branch matching this session.
- No implementation files changed; no package added; no live service contacted;
  no push or remote change performed.
- Build, format, tests, and replay were not run: no implementation exists to
  validate, and this is the task's prescribed hard-stop path.

## Decision needed

The conductor must explicitly allow the session report, log, improvements,
status, and halt paths in its ownership rules and mechanical gate, or change
their required locations to owned paths. After that correction, rerun the
session from S1 with the full preflight; this run supplies no adapters or
integration guarantees.
