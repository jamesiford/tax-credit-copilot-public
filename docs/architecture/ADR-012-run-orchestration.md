# ADR-012 — Run orchestration

**Date** 2026-11-12 · **Status** Proposed (built and tested offline; not yet run against a live Warehouse, and a person accepts it) ·
**Relates to** [ADR-003](ADR-003-clean-architecture-cqrs.md) (mediator pipeline), [ADR-007](ADR-007-warehouse-operational-store.md)
(operational store), [ADR-011](ADR-011-azure-sql-operational-store.md) (platform choice), [ADR-013](ADR-013-program-registry.md)
(program registry). Operator guide: [RUN-ORCHESTRATION.md](RUN-ORCHESTRATION.md).

This record matches the code as built. Where the first design differed, the built behaviour is described and the change is noted.

## Context

A client is calculated by `POST /api/v2/clients/{id}/runs`, which runs the engine inside the HTTP request and returns when
Gold is written. That suits one client at an operator's request. Onboarding a large book needs the same work for a selection,
a filtered group or every client, with progress, retry and cancel, and from the Microsoft 365 channel, whose tokens are
refused on the run routes. Three constraints shape the design:

- A run for one client-year replays every authored year of that client's payroll and writes Gold for all of them, but records a
  manifest for the requested year only. The manifest is the unit of "has this been done", and a new manifest supersedes the
  earlier one per (client, program), not per year.
- Gold writes conflict on Fabric Warehouse (error 24556) when two transactions touch the same table; two runs for the same
  client can leave mixed `is_current` rows.
- `calculation_id` digests one year's payroll, so on its own it cannot show that a **prior** year was restated.

## Decision

1. **Batch model in `tcc_ops`** (migration `0004`): `run_batch` (one row per request) and `run_batch_item` (one row per client and
   program, optionally a year). Portable T-SQL, one shared SQL store serving SQLite and the Warehouse. The queue follows
   `RUN_MANIFEST_STORE`; there is no new store setting. The statements are cross-client by nature and go through one named
   `tenant_exempt` reason. (Names differ from the first draft, which said `run_job`.)
2. **Queue with leases.** A worker claims queued items with a conditional update and holds a lease (default 120 s) renewed by a
   heartbeat; an expired lease returns the item to `queued`. **Per-client lock**: an item is claimable only when no other item of
   that client holds a live lease, with an `item_id` tie-break between racing claimers. This is airtight on SQLite and only
   **narrowed** on the Warehouse under snapshot isolation; it is not proven there (live check).
3. **Worker is a separate entry point**, `python -m bootstrap.run_worker` (`scripts/run-worker.py`), not `application.runs.worker`:
   `application` may not import `bootstrap`, so the framework-free worker lives in `application/runs/worker.py` and the entry
   point composes it. An inline worker thread starts only when `ENVIRONMENT=local` (or when set explicitly, for a single-instance
   trial). Terraform for a separate worker app is default off (`enable_run_worker`).
4. **Modes.** `calculate` dispatches `RunClientCalculationCommand`, `assess` dispatches `AssessClientCommand`,
   `assess_and_calculate` does both. The existing run and assess endpoints are unchanged.
5. **One item per (client, program).** A client with payroll in several states that each have a calculable program is run for each,
   derived from the client book's footprint and the registry with no payroll scan; a named `program_code` applies to everyone;
   `refresh_once` (default true) makes one item per client rather than per client-year, because every run refreshes every year.
   `refresh_once=false` needs explicit years. An item with no year resolves to the client's default year when it starts.
6. **Selection.** Explicit ids, a filter in the portfolio's own vocabulary, or all clients, resolved from the book, claims and
   footprint, never from payroll, and narrowed to the clients the caller may act for (a named client they may not act for is
   refused).
7. **Skipping unchanged is opt-in** (`skip_unchanged`, default **false**; `force` is kept and wins). It needs, on the latest
   successful manifest for the client and program: the same tax year, the same `calculation_id`, the same assumption SHA-256s and
   `rule_pack_version` (and `code_commit` only on request), and the same **client-wide data fingerprint**, a digest of all the
   client's payroll inside any authored year's fiscal window, which a run stores in the manifest's `source_snapshot_id`. A manifest
   without it means "cannot tell, so run", so the first batch after a release cannot skip anything. The preview reports
   `skip_coverage` and only an upper bound, never a promised count. Limit: the supersede is per (client, program), so "unchanged"
   speaks for the latest manifest only.
8. **State machines.** Batch: `queued -> running -> (succeeded | partial | failed | cancelled)`, derived from the items. Item:
   `queued -> leased -> running -> (succeeded | skipped_unchanged | skipped_no_payroll | failed | cancelled)`, `failed -> queued` on
   retry. Cancel is cooperative: queued items become `cancelled`, a running item finishes.
9. **Failures.** A transient failure (store unreachable, timeout, write conflict) is retried with capped backoff and jitter up to
   `RUN_ITEM_MAX_ATTEMPTS`. A request the data cannot satisfy is a skip with the reason, never a failure and never a zero. A Gold
   write that does not validate (section 9: for example more than one current run for a client and program) fails with the named
   cause `gold_write` and a remedy, and is retried **once** with no other worker on the client; a second failure stays failed and
   visible.
10. **API (typed models), `/api/v2/run-batches`.** `POST` starts a batch, or with `dry_run` previews it and writes nothing;
    `GET` lists, `GET /{id}` reads one, `GET /{id}/items` pages its items, `POST /{id}/cancel`, `POST /{id}/retry-failed`.
    Starting is a command with `Policy.WRITER` and every account named is authorised; the write routes are refused to an agent
    token. Confirmation is typed: above `RUN_BATCH_CONFIRM_ABOVE` the start must send `confirm_items` equal to the count.
11. **Safety defaults.** Size cap `RUN_BATCH_MAX_ITEMS` (only scope `all` may override it); idempotency by key and by an identical
    open batch; `RUN_WORKER_CONCURRENCY` defaults to **1** (maximum 8) until concurrent Gold writes are measured on a live
    Warehouse; every start, cancel and retry is audited, failures included.
12. **Channel.** `run_batch_prepare` and `run_batch_commit` form a two-step write (the preview is the dry run and always comes
    first; above the confirmation threshold it refuses with the counts until `confirm_items` is supplied); `run_batch_status` and
    `run_batch_list` are reads. The model-facing schemas carry no `client_id`: a batch's accounts travel as `scope.account_ids`.
13. **Portal.** Selection and a start dialog on the book (preview first, typed confirmation, an unchecked "skip unchanged"
    option), a Runs page with progress, failures by cause, cancel and retry, and an opt-in single-client batch mode
    (`VITE_RUN_AS_BATCH` or `localStorage['tcc.run-as-batch']`, off by default).

## Failure modes

| Failure | Result |
|---|---|
| Worker dies mid-item | The lease lapses and the item returns to the queue; a rerun writes a new `run_id` that supersedes; the existing reaper closes a stranded `running` manifest |
| Writer conflict persists | The item is retried with backoff up to the attempt limit, then `failed` with cause `conflict` |
| Gold write does not validate | `failed` with cause `gold_write`, retried once with no other worker on the client, then stays failed |
| Client has no payroll or an unauthored year | `skipped_no_payroll` with the reason |
| Same request twice | The same batch is returned |
| Fabric or SQL unavailable | `DependencyUnavailable`: the API answers degraded and items stay queued; the status read shows a degraded `run_worker` entry when queued work has no live lease |

## Consequences

Batches survive restarts and scale-out, and the interactive endpoints keep their behaviour. A worker must be deployed for batches to
progress outside local development. Live checks remain: concurrent Gold writes and the per-client lock on a Warehouse, migration
`0004` on a real store, a real batch compared with a single run, and the Teams and Cowork republish.

## Deliberately not done

No scheduler or cron triggers; no Fabric notebook or pipeline venue; no change to the engine or to the existing run and assess routes;
no new infrastructure beyond the default-off worker app. (Two programs in one state used to be unrunnable because the run command took a
state; since F04c the command, the planner and the executor carry `program_code`, so each program is its own item and runs under its
own pack.)
