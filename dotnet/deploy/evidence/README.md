# Sanitized local evidence

Publication/images/zips were rebuilt from implementation commit **2e8ba28**,
including the final telemetry hook. Later delivery commits contain evidence,
documentation and status, not product/runtime source changes.

- `images.json`: four actual source-built linux/amd64 image IDs, nonroot user,
  inspected OCI revision and explicit offline-feed selection.
- `container-smoke.json`: final egress-disabled container observations, including
  false-positive readiness and the **unverified emulated Worker abnormal exit**.
- `published-smoke.json`: four ordinary published artifacts; Responses executes
  only in a kernel-isolated Linux namespace. Windows stops are not graceful
  Linux shutdown claims.
- `package-proof.json`: two independently repeated zips of each actual API/
  gateway publication; matching SHA-256, byte/entry counts and manifest revision.
- `provenance.json`: rechecked publication file counts and byte identity of the
  packaged Hook against the actual API/gateway collector receipt.
- `ci-replay-*.json`: unchanged existing semantic policy aggregates. API remains
  blocked; gateway threshold pass is not zero differences. Replay product
  source is unchanged from baseline 006760b; no waiver was added by this task.

Actual-host telemetry receipt evidence is separately retained under
`telemetry/evidence/published-{receiver,collector}.json`. It records the DLL/Hook
hashes actually used. Correlation/exit-flush evidence from the controlled probes
must not be confused with real API/gateway dependency or native transaction
proof. See the telemetry README.

These files contain no raw replay bodies, configuration values, caller/client
identity, prompts, tokens, server names or native data. The initial raw temporary
replay folder and bounded temporary source context were removed after proof.
Published artifacts and local images remain available, ignored/unpushed.
