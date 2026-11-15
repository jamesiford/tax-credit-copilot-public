# Persistence hard stop: conflicting writable paths

Session: `persistence`
Branch: `dotnet/w1-persistence`
Initial HEAD: `b8e17f4`

## What happened

The complete task description was read from the supplied prompt. Its fixed
writable-path rule permits changes only in:

- `dotnet/src/TaxCredit.Infrastructure.Persistence/**`
- `dotnet/tests/TaxCredit.Infrastructure.Persistence.Tests/**`
- `dotnet/src/TaxCredit.Application/Ports/Persistence/**`
- `dotnet/Directory.Packages.props`

The same task requires `dotnet/docs/PERSISTENCE-REPORT.md`, a running
`dotnet/docs/persistence-log.md`, deliberate-difference registration under
`dotnet/docs/improvements/`, and `dotnet/docs/status/persistence.json`.
None is inside that allowlist. It explicitly states that any other change
fails the owned-path gate and requires a hard stop when a change outside
owned paths would be needed.

Hard stop 1 therefore applies before implementation. This halt report and
the finish status are written solely under the explicit hard-stop/finish
instructions, not as an inferred extension of implementation ownership.

## What was checked

- Read the supplied task file in full.
- Confirmed the current branch is `dotnet/w1-persistence`.
- Confirmed the initial working tree is clean.
- Checked for repository `AGENTS.md` files; none were found.
- Inspected central package ownership markers and the prepared persistence
  project directories; these do not supply a documentation-path exception.
- Did not alter product code, packages, remotes, another worktree, or external
  systems. No persistence implementation or gate validation is claimed.

## Required owner/conductor decision

Add the required session-specific documentation files to both the task's
writable-path allowlist and the conductor's owned-path gate, including the
halt and status paths. Alternatively, relocate every required report and
finish file into the existing owned paths and update the conductor checks
accordingly. The current instructions cannot both be satisfied exactly.

Stages P1-P6 remain unstarted. Resume implementation after ownership is
consistent; there is no new persistence API or registration for other
sessions to consume.
