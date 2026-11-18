/* ============================================================================
   .NET host operational objects for tcc_ops (Fabric Warehouse; Azure SQL: see the note at the end)

   The .NET host (TaxCredit.Api / TaxCredit.Worker) needs five objects that the Python migrations 0001 to 0005 do not
   create. dotnet/docs/COMPOSITION-SCHEMA-PROVISIONING.md is the specification; this file is its T-SQL.

     tcc_ops.write_sequence            one row, 'manual_override': the transactional counter behind manual_override.write_order
     tcc_ops.manual_override.write_order   BIGINT, filled for every historical row, allocated from write_sequence for each new append
     tcc_ops.run_work_identity         the run id chosen for a queue item, so a retry reuses it
     tcc_ops.run_source_observation    the small source fingerprint JSON recorded with each run (no payroll, no employee data)
     tcc_ops.finding_audit             who reopened which finding, and when

   Idempotent: every statement is guarded, so a re-run changes nothing. Additive: it does not touch existing rows except to
   fill write_order. Run it with writers stopped (API and Worker), through the guarded runner:

     python scripts/run-sql.py --target deployed --file dotnet/deploy/sql/0100_dotnet_operational_objects.sql

   Historical rows with identical timestamps have no stored true order; the backfill orders them by created_at, override_id,
   client_id, which is deterministic, not a reconstruction of intent. Keys are NOT ENFORCED, as in the bootstrap (Fabric).
   For Azure SQL Database remove the words NOT ENFORCED (the same one-line strip the repository's other migrations use).
   ============================================================================ */

IF OBJECT_ID('tcc_ops.write_sequence', 'U') IS NULL
    CREATE TABLE tcc_ops.write_sequence
    (
        sequence_name VARCHAR(64) NOT NULL,
        last_value    BIGINT      NOT NULL
    );
GO

IF NOT EXISTS (SELECT 1 FROM tcc_ops.write_sequence WHERE sequence_name = 'manual_override')
    INSERT INTO tcc_ops.write_sequence (sequence_name, last_value) VALUES ('manual_override', 0);
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'tcc_ops' AND TABLE_NAME = 'manual_override' AND COLUMN_NAME = 'write_order')
    ALTER TABLE tcc_ops.manual_override ADD write_order BIGINT NULL;
GO

UPDATE m
SET write_order = o.rn
FROM tcc_ops.manual_override AS m
INNER JOIN
(
    SELECT override_id, client_id,
           ROW_NUMBER() OVER (ORDER BY created_at, override_id, client_id)
               + (SELECT COALESCE(MAX(write_order), 0) FROM tcc_ops.manual_override) AS rn
    FROM tcc_ops.manual_override
    WHERE write_order IS NULL
) AS o ON o.override_id = m.override_id AND o.client_id = m.client_id
WHERE m.write_order IS NULL;
GO

UPDATE tcc_ops.write_sequence
SET last_value = (SELECT COALESCE(MAX(write_order), 0) FROM tcc_ops.manual_override)
WHERE sequence_name = 'manual_override'
  AND last_value < (SELECT COALESCE(MAX(write_order), 0) FROM tcc_ops.manual_override);
GO

IF OBJECT_ID('tcc_ops.run_work_identity', 'U') IS NULL
    CREATE TABLE tcc_ops.run_work_identity
    (
        client_id BIGINT      NOT NULL,
        item_id   VARCHAR(64) NOT NULL,
        run_id    VARCHAR(64) NOT NULL
    );
GO

IF OBJECT_ID('tcc_ops.run_source_observation', 'U') IS NULL
    CREATE TABLE tcc_ops.run_source_observation
    (
        client_id        BIGINT        NOT NULL,
        run_id           VARCHAR(64)   NOT NULL,
        observation_json VARCHAR(8000) NOT NULL
    );
GO

IF OBJECT_ID('tcc_ops.finding_audit', 'U') IS NULL
    CREATE TABLE tcc_ops.finding_audit
    (
        audit_id   VARCHAR(64)  NOT NULL,
        client_id  BIGINT       NOT NULL,
        finding_id VARCHAR(128) NOT NULL,
        action     VARCHAR(16)  NOT NULL,
        actor      VARCHAR(256) NOT NULL,
        at         VARCHAR(40)  NOT NULL
    );
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = 'tcc_ops' AND CONSTRAINT_NAME = 'pk_write_sequence')
    ALTER TABLE tcc_ops.write_sequence ADD CONSTRAINT pk_write_sequence PRIMARY KEY NONCLUSTERED (sequence_name) NOT ENFORCED;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = 'tcc_ops' AND CONSTRAINT_NAME = 'pk_run_work_identity')
    ALTER TABLE tcc_ops.run_work_identity ADD CONSTRAINT pk_run_work_identity PRIMARY KEY NONCLUSTERED (client_id, item_id) NOT ENFORCED;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = 'tcc_ops' AND CONSTRAINT_NAME = 'pk_run_source_observation')
    ALTER TABLE tcc_ops.run_source_observation ADD CONSTRAINT pk_run_source_observation PRIMARY KEY NONCLUSTERED (client_id, run_id) NOT ENFORCED;
GO

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = 'tcc_ops' AND CONSTRAINT_NAME = 'pk_finding_audit')
    ALTER TABLE tcc_ops.finding_audit ADD CONSTRAINT pk_finding_audit PRIMARY KEY NONCLUSTERED (audit_id) NOT ENFORCED;
GO

