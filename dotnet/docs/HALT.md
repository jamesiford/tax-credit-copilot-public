# Platform spike halted: ScratchGuard self-test failed

**Leftover scratch objects: unknown.** No Fabric connection was opened, so
pre-existing objects could not be inventoried. This run created no scratch
objects. Cleanup is **not proven**.

The mandatory offline self-test returned exit code 2 with
`InvalidOperationException`. The guard's negative-test loop throws this
exception when a forbidden statement is unexpectedly accepted. The current
diagnostic does not identify the failing case; do not infer which one failed.

This triggers hard stop 1 in the task description. No live SQL, token acquisition,
Fabric REST call, Python baseline, write experiment or lakehouse read was
attempted. Do not bypass the self-test or run the experiments from this revision.

The isolated solution builds with zero warnings and errors, but a successful
build is not a successful safety test. The self-test did not pass. Investigation
and repair of the guard require a separate run before connectivity can begin.

The approval gate was `yes`. Azure CLI was signed in, .NET SDK 10.0.404 and the
Python oracle were present, and Docker reported a Linux engine. The CLI tenant's
access to the demo Fabric was not verified; capacity status was not checked.

The standalone `cleanup` command exists but also runs the mandatory self-test
first and therefore refuses live access in this revision. No cleanup attempt
was made after the hard stop. Do not resume or otherwise modify the capacity.
