# ADR-012 — Run orchestration

**Date** 2026-11-12 · **Status** Proposed (design; implemented in later steps, not yet run against a live Warehouse) ·
**Relates to** [ADR-003](ADR-003-clean-architecture-cqrs.md) (mediator pipeline), [ADR-007](ADR-007-warehouse-operational-store.md)
(operational store), [ADR-011](ADR-011-azure-sql-operational-store.md) (platform choice).

## Context

A client is calculated by `POST /api/v2/clients/{id}/runs`, which runs the engine inside the HTTP request and returns when
Gold is written. That suits one client at an operator's request. Onboarding a large book needs the same work for a selection,
a filtered group or every client, with progress, retry and cancel, and from the Microsoft 365 channel, whose tokens are
refused on the run routes. Three constraints shape the design:

- A run for one client-year replays every year of that client's payroll and writes Gold for all of them, but records a manifest
  for the requested year only. The manifest is the unit of "has this been done".
- Gold writes conflict on Fabric Warehouse (error 24556) when two transactions touch the same table; two runs for the same
  client can leave mixed `is_current` rows.
- The source snapshot id on the manifest is never populated, so it cannot say "nothing changed".

## Decision

1. **Job model in `tcc_ops`** (migration 0004): `run_job` (one row per batch: mode, scope, resolved-set hash, years, options,
   state, counts, requested_by, idempotency key, timestamps) and `run_job_item` (one row per client-year: state, attempts,
   lease owner and expiry, manifest run id, outcome, reason). Portable T-SQL, tenant-bound through `tenant_sql`.
2. **Queue with leases.** A worker claims queued items with a conditional `UPDATE`, holds a lease (default 120 s) renewed by
   a heartbeat; an expired lease returns the item to `queued`. **Per-client lock**: an item is claimable only when no other
   item of that client holds a live lease.
3. **Worker is a separate entry point** (`python -m workers.run_worker`) sharing the application code and the mediator. An
   inline worker thread runs only when `ENVIRONMENT=local`. Deploying the worker as its own process is an operator step.
4. **Modes.** `calculate` dispatches `RunClientCalculationCommand`; `assess` dispatches `AssessClientCommand`. The existing
   endpoints are unchanged.
5. **Selection.** `ids`, `filter` (the portfolio filter expression, resolved from the book, claims and manifests, never from
   payroll) or `all`; years are explicit or "every year the client holds". The resolved client set and its hash are stored.
6. **Unchanged skipping.** An item is `skipped_unchanged` only when the latest successful manifest for (client, program, year)
   has the same `calculation_id`, the same assumption hashes and the same `rule_pack_version` (and, if asked, `code_commit`).
   Any value missing means "cannot tell": the item runs. `force` disables the check.
7. **State machines.** Job: `queued -> running -> (succeeded | partial | failed | cancelled)`; item: `queued -> running ->
   (succeeded | skipped_unchanged | not_available | failed | cancelled)`, `failed -> queued` on retry (max attempts 3, backoff).
   Cancel is cooperative: queued items become `cancelled`; a running item finishes (a half-written run is never abandoned).
8. **API (typed models).** `POST /api/v2/run-jobs/preview` (no writes: count, skipped estimate, confirmation need),
   `POST /api/v2/run-jobs` (start; `idempotency_key`; `confirm_count` above `RUN_BATCH_CONFIRM_ABOVE`),
   `GET /api/v2/run-jobs`, `GET /api/v2/run-jobs/{id}` (counts, items page), `POST /api/v2/run-jobs/{id}/cancel`,
   `POST /api/v2/run-jobs/{id}/retry-failed`. Starting is a command with `Policy.WRITER`; the same command backs the channel.
9. **Safety.** Size cap `RUN_BATCH_MAX_ITEMS`; typed confirmation above the threshold; idempotency by key and by identical
   open job; global concurrency `RUN_WORKER_CONCURRENCY` (default 2, maximum 8); every start, cancel and retry is audited,
   failures included.
10. **Channel.** `run_batch_start` is a two-step `WriteSpec` (preview states the count, mode, years and the unchanged
    estimate); `run_batch_status` is a read capability.

## Failure modes

| Failure | Result |
|---|---|
| Worker dies mid-item | Lease expires, item re-queued; the run is idempotent (new `run_id` supersedes); a stranded `running` manifest is reaped by the existing reaper |
| Writer conflict persists | Item `failed` (retryable), re-queued with backoff up to the attempt limit |
| Client has no payroll / unauthored year | `not_available` with the reason, never `failed`, never a zero |
| Same request twice | Same job returned |
| Fabric/SQL unavailable | `DependencyUnavailable`: the API answers degraded, items stay queued |

## Consequences

Batches survive restarts and scale-out; the interactive endpoints keep their behaviour. A worker must be deployed for jobs
to progress outside local development, and a live Warehouse check of concurrent writes is required before raising
concurrency above the default.

## Deliberately not done

No scheduler or cron triggers; no Fabric notebook or pipeline venue; no change to the engine or to the existing run and
assess routes; no new infrastructure resource.
