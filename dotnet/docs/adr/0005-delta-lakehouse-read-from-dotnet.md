# ADR 0005: Reading the Delta lakehouse from .NET

Status: **proposed; not decided.** The spike deliberately does not choose. Date: 2026-11-14.

## Context

Python reads payroll from the Fabric Lakehouse (OneLake, Delta, `deltalake[pyarrow]`), and has a spike for the SQL
analytics endpoint (`SOURCE_READ_MODE=sql`, `docs/architecture/SQL-READ-PATH.md`). That spike records its own open gap:
**the SQL endpoint exposes no Delta version**, so a run cannot state which data it read, and metadata sync can lag the
Delta tables by seconds to minutes.

## Options

| # | Option | For | Against / unknown |
|---|---|---|---|
| A | **Fabric SQL analytics endpoint over ADO.NET** (`Microsoft.Data.SqlClient`, Entra token) | Viewer role is enough (no write-capable role on a payroll workspace); `SqlDataReader` streams; trivial in .NET; same query shapes as the Python spike | No Delta version (reproducibility gap); sync lag; row-grain throughput against Fabric unmeasured (Python's 169 ms vs 132 s figure was an aggregate against a cold open) |
| B | `DeltaLake.Net` community wrapper over delta-rs (native Rust) | Reads the Delta log and records the version | Pre-1.0, native binaries per RID, not Microsoft supported; maintenance and supply-chain risk. **Verify:** maturity, OneLake auth, long-path and token refresh behaviour |
| C | Hand-rolled Delta log reader + Parquet reader (`Parquet.Net`) | Pure managed; we control version capture | We own protocol correctness (checkpoints, deletion vectors, column mapping); high cost; **verify** Parquet.Net licence and speed |
| D | Sidecar (Python or Rust service exposing rows/Arrow) | Reuses the proven reader; version recorded | Keeps Python in the production path, the thing the port removes |

## What must be verified before deciding

1. Row-grain read throughput and memory over the SQL endpoint for the largest account (about 10 million rows), against a real Fabric capacity.
2. Whether a fingerprint taken in the same statement batch (row count plus latest modified date) is an acceptable stand-in for a Delta version, or whether Silver must carry the build version (Python's preferred option 1).
3. Metadata-sync lag after a load and how the application should wait for it.
4. For B: maintenance posture, binary distribution, OneLake token handling, behaviour on Delta features used by this lakehouse.

## Direction

Treat **A** as the first implementation behind an `IPayrollSource` port (`TaxCredit.Application`), because it needs the least
privilege and the least new code; carry the version-recording gap as a named risk, and keep the port narrow enough that B, C
or D can replace the adapter without touching the engine. The engine consumes rows, never a reader.
