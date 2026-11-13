/* ============================================================================
   0005 — program drafts: proposals to bring on a new tax incentive program

   A draft holds a base pack and year packs (as documents), the last validation and a review decision, and moves
   draft -> needs_changes / ready_for_review -> approved_for_export -> exported (or withdrawn). Drafts have NO runtime
   authority: nothing that calculates reads these tables. A program becomes calculable only when a person commits the
   exported pack files to git and deploys (ADR-005, ADR-013). docs/architecture/PROGRAM-DRAFTS.md.

   Global, not per client: a program is a fact about the platform, so these tables carry no client key and are read
   through an explicit tenant exemption. Documents are one row each (a pack, or one year) so each fits VARCHAR(8000);
   the application refuses a larger document by name rather than truncating it. program_draft_event is append-only.

   Keys are NOT ENFORCED, as in the bootstrap. No CREATE INDEX, IDENTITY or MERGE. The optimistic-concurrency check on
   `version` and the one-live-draft-per-code rule are enforced by the application. The SQL Server variant is the same
   file with `NOT ENFORCED` stripped (scripts/generate-schema-variants.py).
   ============================================================================ */

CREATE TABLE tcc_ops.program_draft
(
    draft_id             VARCHAR(36)    NOT NULL,
    proposed_code        VARCHAR(64)    NOT NULL,
    name                 VARCHAR(200)   NOT NULL,
    jurisdiction_level   VARCHAR(16)    NOT NULL,   -- federal | state | local
    state                VARCHAR(8)     NULL,
    status               VARCHAR(24)    NOT NULL,   -- draft | validating | needs_changes | ready_for_review | approved_for_export | exported | withdrawn
    version              INT            NOT NULL,   -- optimistic concurrency: a write names the version it read
    created_by           VARCHAR(256)   NOT NULL,
    created_at           DATETIME2(3)   NOT NULL,
    updated_by           VARCHAR(256)   NOT NULL,
    updated_at           DATETIME2(3)   NOT NULL,
    validation_json      VARCHAR(8000)  NULL,       -- the last validation: counts, capped findings, and the content hash it covered
    review_requested_by  VARCHAR(256)   NULL,
    reviewer             VARCHAR(256)   NULL,
    decision             VARCHAR(24)    NULL,       -- approve | request_changes
    decision_comment     VARCHAR(2000)  NULL,
    decided_at           DATETIME2(3)   NULL,
    approved_sha256      VARCHAR(64)    NULL,       -- the content hash the reviewer approved
    exported_at          DATETIME2(3)   NULL,
    export_sha256        VARCHAR(64)    NULL        -- the hash of the exported bundle
);
GO

ALTER TABLE tcc_ops.program_draft
    ADD CONSTRAINT pk_program_draft PRIMARY KEY NONCLUSTERED (draft_id) NOT ENFORCED;
GO

CREATE TABLE tcc_ops.program_draft_document
(
    draft_id        VARCHAR(36)    NOT NULL,
    doc_key         VARCHAR(16)    NOT NULL,        -- 'pack' or a tax year such as '2025'
    content_json    VARCHAR(8000)  NOT NULL,        -- canonical JSON
    content_sha256  VARCHAR(64)    NOT NULL
);
GO

ALTER TABLE tcc_ops.program_draft_document
    ADD CONSTRAINT pk_program_draft_document PRIMARY KEY NONCLUSTERED (draft_id, doc_key) NOT ENFORCED;
GO

CREATE TABLE tcc_ops.program_draft_event
(
    draft_id     VARCHAR(36)    NOT NULL,
    seq          INT            NOT NULL,           -- order within the draft
    event_type   VARCHAR(32)    NOT NULL,           -- created | edited | validated | review_requested | approved | changes_requested | withdrawn | exported
    actor        VARCHAR(256)   NOT NULL,
    at           DATETIME2(3)   NOT NULL,
    from_status  VARCHAR(24)    NULL,
    to_status    VARCHAR(24)    NULL,
    detail_json  VARCHAR(4000)  NULL
);
GO

ALTER TABLE tcc_ops.program_draft_event
    ADD CONSTRAINT pk_program_draft_event PRIMARY KEY NONCLUSTERED (draft_id, seq) NOT ENFORCED;
GO
