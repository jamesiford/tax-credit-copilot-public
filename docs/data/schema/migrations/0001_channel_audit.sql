/* ============================================================================
   0001 — channel audit, writer allow-list and write confirmations

   The Microsoft 365 channel's per-user trail. Append-only: a request writes a
   `begin` event (outcome `pending`) before any write commits and an `end` event
   after, linked by audit_id, so a crash still leaves a record. A read writes one
   event with phase `single`.

   channel_user is the writer allow-list. A removal stamps removed_at on the live
   row and nothing else; re-adding inserts a new live row.

   channel_confirmation holds the prepare/commit tokens. Only the SHA-256 of a
   token is stored, never the token.

   Keys are NOT ENFORCED, as in the bootstrap. No CREATE INDEX, IDENTITY or MERGE.
   ============================================================================ */

CREATE TABLE tcc_ops.channel_audit
(
    audit_id              VARCHAR(64)    NOT NULL,
    event_seq             INT            NOT NULL,   -- 1 = begin or single, 2 = end
    phase                 VARCHAR(8)     NOT NULL,   -- begin | end | single
    correlation_id        VARCHAR(64)    NOT NULL,
    occurred_at           DATETIME2(3)   NOT NULL,
    elapsed_ms            INT            NULL,
    channel               VARCHAR(24)    NOT NULL,   -- teams | m365-copilot | cowork | api-test
    user_oid              VARCHAR(64)    NOT NULL,
    tenant_id             VARCHAR(64)    NULL,
    user_display_name     VARCHAR(256)   NULL,
    user_upn              VARCHAR(256)   NULL,
    identity_assurance    VARCHAR(24)    NOT NULL,   -- channel-asserted | delegated
    conversation_id       VARCHAR(128)   NULL,
    tool_name             VARCHAR(64)    NOT NULL,
    action_kind           VARCHAR(16)    NOT NULL,   -- read | write_prepare | write_commit
    client_id             BIGINT         NULL,
    tax_year              INT            NULL,
    request_summary       VARCHAR(2000)  NULL,       -- never payroll content or employee identifiers
    request_sha256        CHAR(64)       NULL,
    confirmation_ref      VARCHAR(64)    NULL,
    outcome               VARCHAR(24)    NOT NULL,   -- pending | ok | error | refused | rejected_by_guard
    error                 VARCHAR(2000)  NULL,
    run_id                VARCHAR(64)    NULL,
    trail_sha256          CHAR(64)       NULL,
    numeric_guard         VARCHAR(8)     NOT NULL,   -- pass | rejected | n/a
    is_deterministic_path BIT            NOT NULL
);
GO

ALTER TABLE tcc_ops.channel_audit
    ADD CONSTRAINT pk_channel_audit PRIMARY KEY NONCLUSTERED (audit_id, event_seq) NOT ENFORCED;
GO

CREATE TABLE tcc_ops.channel_user
(
    user_oid       VARCHAR(64)    NOT NULL,
    display_name   VARCHAR(256)   NULL,
    role           VARCHAR(16)    NOT NULL,          -- writer
    added_by       VARCHAR(256)   NOT NULL,
    added_at       DATETIME2(3)   NOT NULL,
    removed_at     DATETIME2(3)   NULL
);
GO

CREATE TABLE tcc_ops.channel_confirmation
(
    confirmation_id  VARCHAR(64)    NOT NULL,
    token_sha256     CHAR(64)       NOT NULL,        -- the hash only; the token is never stored
    user_oid         VARCHAR(64)    NOT NULL,
    tool_name        VARCHAR(64)    NOT NULL,
    args_sha256      CHAR(64)       NOT NULL,
    idempotency_key  VARCHAR(128)   NULL,
    created_at       DATETIME2(3)   NOT NULL,
    expires_at       DATETIME2(3)   NOT NULL,
    consumed_at      DATETIME2(3)   NULL,
    outcome          VARCHAR(16)    NULL,
    result_json      VARCHAR(8000)  NULL             -- for idempotent replays
);
GO

ALTER TABLE tcc_ops.channel_confirmation
    ADD CONSTRAINT pk_channel_confirmation PRIMARY KEY NONCLUSTERED (confirmation_id) NOT ENFORCED;
GO
