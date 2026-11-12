/* ============================================================================
   0003 — app-owned lookup overrides and their audit trail

   The app resolves four lookups the customer's schema does not carry (pay-code category, fiscal-year rules,
   pay frequency, industry type) through one resolver: source, then override, then seed, then default. This is the
   override layer: rows the app owns, per client (client_id = the account) or global (client_id = 0), with
   provenance and effective dates. Nothing is authored in the customer's lakehouse.

   lookup_override is append-style: a new value for a key sets superseded_at on the live row and inserts the new
   one; a removal sets superseded_at and inserts nothing. lookup_audit records every change and never changes.

   Keys are NOT ENFORCED, as in the bootstrap. No CREATE INDEX, IDENTITY or MERGE.
   ============================================================================ */

CREATE TABLE tcc_ops.lookup_override
(
    override_id     VARCHAR(36)    NOT NULL,
    lookup_name     VARCHAR(64)    NOT NULL,   -- pay_code_category | entity_fiscal_year_rules
    client_id       BIGINT         NOT NULL,   -- the account; 0 = global default
    key_kind        VARCHAR(16)    NOT NULL,   -- code | category | rule
    key_value       VARCHAR(256)   NOT NULL,   -- normalised pay-code text, category id, or entity id / 'default'
    value_json      VARCHAR(2000)  NOT NULL,   -- canonical category, or the fiscal rule as a JSON object
    effective_from  DATE           NULL,
    effective_to    DATE           NULL,
    authored_by     VARCHAR(256)   NOT NULL,
    authored_on     DATETIME2(3)   NOT NULL,
    basis           VARCHAR(1000)  NULL,
    inferred        BIT            NOT NULL,
    superseded_at   DATETIME2(3)   NULL
);
GO

ALTER TABLE tcc_ops.lookup_override
    ADD CONSTRAINT pk_lookup_override PRIMARY KEY NONCLUSTERED (override_id) NOT ENFORCED;
GO

CREATE TABLE tcc_ops.lookup_audit
(
    audit_id        VARCHAR(36)    NOT NULL,
    lookup_name     VARCHAR(64)    NOT NULL,
    client_id       BIGINT         NOT NULL,
    action          VARCHAR(16)    NOT NULL,   -- put | remove
    key_kind        VARCHAR(16)    NOT NULL,
    key_value       VARCHAR(256)   NOT NULL,
    value_json      VARCHAR(2000)  NULL,
    actor           VARCHAR(256)   NOT NULL,
    at              DATETIME2(3)   NOT NULL,
    basis           VARCHAR(1000)  NULL
);
GO

ALTER TABLE tcc_ops.lookup_audit
    ADD CONSTRAINT pk_lookup_audit PRIMARY KEY NONCLUSTERED (audit_id) NOT ENFORCED;
GO
