# Skeleton hard stop: report paths excluded from ownership

The complete task description requires `dotnet/docs/HOST-ARCHITECTURE.md`,
`dotnet/docs/route-groups.json`, improvements registers, and a running log.
Its fixed owned-path allowlist permits source and test directories and two
build configuration files, but no `dotnet/docs/**` paths. It explicitly says
any other change fails the owned-path gate.

Hard stop 1 applies: completing the required deliverables would require
changes outside the owned paths. The missing-decision policy cannot override
the fixed rules or hard stops.

## Evidence and actions

- Read the entire supplied task description.
- Verified the worktree is clean, on `dotnet/w1-skeleton`, at `b8e17f4`.
- Listed the existing documentation: the required skeleton reports do not
  exist, so this is not resolvable by leaving existing reports untouched.
- Made no product, infrastructure, dependency, or test changes.
- Did not run build, format, tests, or replay: implementation stopped before
  preflight because the mandatory output paths are forbidden.
- Created only the stop report, finish status, and session log explicitly
  required by the stopping instructions. No push or remote change was made.

## Required owner decision

Authorize the skeleton session's required report, log, improvements, and
status paths under `dotnet/docs/` in the owned-path allowlist and its
mechanical gate. Clarify whether the improvements register is
`improvements/W1-skeleton.json` (Stage 4) or `improvements/skeleton.json`
(fixed rules). Then resume the session for preflight and implementation.
