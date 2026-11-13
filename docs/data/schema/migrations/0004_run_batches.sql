/* ============================================================================
   0004 — run batches: tracked, retryable, cancellable work

   A batch is one request to assess and/or calculate a set of clients (one, a list, a filtered group or all).
   An item is one client, optionally one tax year (NULL tax_year = "the client's latest runnable year", resolved
   when the item starts). Workers claim queued items with a lease; the lease and heartbeat columns are what let
   an item come back after a worker dies. docs/architecture/ADR-012-run-orchestration.md.

   Items are updated in place (status, attempts, lease): they are a work queue, not a ledger. The ledger of what
   was computed is tcc_ops.run_manifest, which each succeeded item links to by run_id. Nothing here is deleted.

   Keys are NOT ENFORCED, as in the bootstrap. No CREATE INDEX, IDENTITY or MERGE. Uniqueness of the idempotency
   key and of a client's single live lease is checked by the application, not by the engine.
   ============================================================================ */

CREATE TABLE tcc_ops.run_batch
(
    batch_id            VARCHAR(36)    NOT NULL,
    kind                VARCHAR(24)    NOT NULL,   -- assess | calculate | assess_and_calculate
    scope_kind          VARCHAR(8)     NOT NULL,   -- one | list | filter | all
    scope_spec          VARCHAR(4000)  NOT NULL,   -- JSON: the ids or the filter, as requested
    program_code        VARCHAR(64)    NULL,
    tax_years           VARCHAR(200)   NULL,       -- JSON array; NULL = latest runnable year per client
    force_run           BIT            NOT NULL,   -- skip the unchanged check
    include_code_commit BIT            NOT NULL,   -- compare code_commit when judging unchanged
    refresh_once        BIT            NOT NULL,   -- one item per client rather than per client-year
    status              VARCHAR(16)    NOT NULL,   -- queued | running | succeeded | partial | failed | cancelled
    cancel_requested    BIT            NOT NULL,
    items_total         INT            NOT NULL,
    items_queued        INT            NOT NULL,
    items_running       INT            NOT NULL,   -- leased or running
    items_succeeded     INT            NOT NULL,
    items_skipped       INT            NOT NULL,
    items_failed        INT            NOT NULL,
    items_cancelled     INT            NOT NULL,
    requested_by        VARCHAR(256)   NOT NULL,
    requested_at        DATETIME2(3)   NOT NULL,
    started_at          DATETIME2(3)   NULL,
    finished_at         DATETIME2(3)   NULL,
    idempotency_key     VARCHAR(128)   NULL,
    dry_run_summary     VARCHAR(4000)  NULL        -- what the preview said when the batch was started
);
GO

ALTER TABLE tcc_ops.run_batch
    ADD CONSTRAINT pk_run_batch PRIMARY KEY NONCLUSTERED (batch_id) NOT ENFORCED;
GO

CREATE TABLE tcc_ops.run_batch_item
(
    item_id             VARCHAR(36)    NOT NULL,
    batch_id            VARCHAR(36)    NOT NULL,
    seq                 INT            NOT NULL,   -- order within the batch
    client_id           BIGINT         NOT NULL,
    program_code        VARCHAR(64)    NULL,
    tax_year            INT            NULL,
    status              VARCHAR(24)    NOT NULL,   -- queued | leased | running | succeeded | skipped_unchanged | skipped_no_payroll | failed | cancelled
    attempts            INT            NOT NULL,
    lease_owner         VARCHAR(128)   NULL,
    lease_expires_at    DATETIME2(3)   NULL,
    heartbeat_at        DATETIME2(3)   NULL,
    not_before          DATETIME2(3)   NULL,       -- retry backoff: not claimable before this instant
    run_id              VARCHAR(36)    NULL,       -- the manifest this item produced
    skip_reason         VARCHAR(500)   NULL,
    error_dependency    VARCHAR(64)    NULL,
    error_message       VARCHAR(1000)  NULL,
    started_at          DATETIME2(3)   NULL,
    finished_at         DATETIME2(3)   NULL
);
GO

ALTER TABLE tcc_ops.run_batch_item
    ADD CONSTRAINT pk_run_batch_item PRIMARY KEY NONCLUSTERED (item_id) NOT ENFORCED;
GO
