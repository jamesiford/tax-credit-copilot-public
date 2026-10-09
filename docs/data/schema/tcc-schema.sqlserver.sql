/* ============================================================================
   GENERATED FILE — DO NOT EDIT

   Produced from tcc-schema.fabric.sql by generate_variants.py.
   Hand-edits are lost on the next run and silently desynchronise the two
   platforms. Change the Fabric file and regenerate.

   Differences from the Fabric source, and only these:
     - NOT ENFORCED removed, so every primary key is genuinely enforced
     - the section 1a access patterns emitted as real CREATE INDEX statements

   Still worth doing by hand on this target, because SQL Server supports what
   Fabric does not: promote the CONSTRAINT INTENT blocks to real CHECK
   constraints, and make the "one current row" uniqueness a filtered unique
   index. On Fabric those are validation queries; here they can be constraints.
   ============================================================================ */

/* ============================================================================
   Tax Credit Copilot — enrichment & operational schema
   Target: Microsoft SQL Server 2016 or later  (GENERATED — see banner)

   Version:   2.0 — Platform v2 as built ("after")
   Date:      2026-10-09
   Derived:   from v1.2 (repo docs/data/schema/flex-schema.fabric.sql, 2026-09-24)
   Status:    AS BUILT — executed against the demo Fabric Warehouse on
              2026-10-08. Bootstrap 0000 recorded; a second migration pass had
              zero pending; all 25 section-9 result sets were empty. Five demo
              clients were recalculated, and Gold reproduced the certified
              10,236 / 539 / 656 figures. The SQL Server companion is generated
              from this file; DDL 2.0 was not separately executed on SQL Server.

   ----------------------------------------------------------------------------
   WHAT CHANGED IN 2.0
   ----------------------------------------------------------------------------

   1. COSMOS DB IS RETIRED. The warehouse is now the ONLY operational store.
      Only three of the ten Cosmos containers were ever written by the
      application, and all three already had a table here:

        | Cosmos container | Used | Now                                      |
        |------------------|------|------------------------------------------|
        | programClaims    | yes  | tcc_ops.program_claim (+ is_base_year)   |
        | engagements      | yes  | tcc_ops.program_engagement               |
        | findings         | yes  | tcc_ops.agent_finding_resolution         |
        | runManifests     | no   | tcc_ops.run_manifest (already the store) |
        | snapshots        | no   | tcc_ops.source_snapshot                  |
        | tenants          | no   | dropped — the source Account table       |
        | decisions        | no   | dropped — see manual_override /          |
        |                  |      |   agent_finding_resolution               |
        | proposals        | no   | dropped — never written                  |
        | scenarios        | no   | dropped — what-if is in-memory by design |
        | checkpoints      | no   | dropped — never written (was TTL 30 d)   |

      Cosmos-only behaviours and their replacements:
        partition key /tenantId  -> client_id leads every predicate; enforced
                                    in the repository base class and by a test
        TTL                      -> none needed (no TTL container was in use)
        change feed              -> none needed (not consumed)
        ETag concurrency         -> Fabric snapshot isolation; the adapter
                                    retries on write-write conflict

   2. program_claim.is_base_year BIT NOT NULL. The only field the Cosmos and
      SQLite adapters held that the warehouse table did not. Net-new needs a
      prior year, so the earliest year's identified figure is zero by
      construction and must not be compared with a filed amount.

   3. NEW GROUP G — ARTIFACTS. Blob Storage now has a real job (source rule
      documents in, claim packages out), and the only way to a blob is through
      the API. Two tables make that governable:
        artifact          what is in Blob, whose it is, and where it came from
        artifact_access   who downloaded what, and when

   4. SCHEMAS RENAMED for the white-label release to tcc_gold / tcc_ops.
      Both names are configuration (GOLD_SCHEMA, OPS_SCHEMA). The customer's
      SOURCE (Bronze) schema is NOT ours and is not renamed — it is a parameter
      (SOURCE_SCHEMA). In this file, references such as "flex.Account" denote
      that source schema as one customer names it.

   ============================================================================
   WHAT THIS IS
   ============================================================================

   The enrichment and operational schema for Tax Credit Copilot:
   tables (24) covering run provenance, calculation results, exclusions and
   overrides, rule history, agent and user activity, claim outcomes, and the
   artifacts the application stores in Blob. It is the application's ONLY
   read/write store. Payroll is read from the source lakehouse; nothing here
   copies it.

   ============================================================================
   THE READ/WRITE CONTRACT
   ============================================================================

   tcc_gold   THE NUMBERS ON THE SCREEN. Written by a calculation run (or, later,
              the customer's pipeline), read by every page. No calculation runs
              on a page load.
   tcc_ops    EVERYTHING ABOUT HOW THE NUMBERS CAME TO BE, plus the commercial
              record: run provenance, exclusions, overrides, rule versions,
              agent actions, claim status, finding decisions, artifacts.
              Written interactively, read by key.

       source payroll --> [ENGINE, on demand, per client] --> tcc_gold
                                    |                             |
                                    +--> tcc_ops     every screen reads

   1. The Gold tables hold everything a screen shows.
   2. Absence of a run is a state, not a zero.
   3. Every row carries run_id, and a rerun supersedes rather than overwrites.
   4. tcc_ops history is APPEND-ONLY: a change inserts a row and stamps the
      prior one closed (effective_to / superseded_at). Nothing else is updated
      in place.

   ============================================================================
   TABLE INVENTORY
   ============================================================================

   | Group | Table                    | Grain                                 |
   |-------|--------------------------|---------------------------------------|
   | A     | run_manifest             | one calculation run                   |
   | A     | source_snapshot          | the payroll a run consumed            |
   | A     | source_file_manifest     | one file or partition in a snapshot   |
   | B     | employee_period_fact     | employee x pay period                 |
   | B     | employee_eligibility     | employee x method x year              |
   | B     | onezero_matrix           | employee x unit x method              |
   | B     | unit_month_summary       | unit x method x year, twelve months   |
   | B     | run_method_summary       | client x year x method, headline      |
   | B     | unit_year_master         | unit x method x year, cross-year      |
   | B     | unit_credit_installment  | creation year x claimable year        |
   | C     | excluded_record          | one excluded payroll row              |
   | C     | manual_override          | one human adjustment                  |
   | C     | exception_report_item    | one flagged anomaly                   |
   | D     | assumption_set_version   | one version of our reading of a rule  |
   | D     | rule_pack_version        | one version of the statute            |
   | D     | rule_change_audit        | one rule change                       |
   | E     | agent_action_audit       | one agent invocation                  |
   | F     | program_claim            | client x program x tax year           |
   | F     | program_engagement       | client x program                      |
   | F     | agent_finding_resolution | one human decision on a finding       |
   | G     | artifact                 | one blob                       (NEW)  |
   | G     | artifact_access          | one download                   (NEW)  |
   | G     | schema_migration         | one applied schema change      (NEW)  |
   | —     | client_config            | client, effective-dated               |

   Group B is the read schema. A, C, D, E and G are audit substrate. F is the
   commercial record and backs the portfolio view.

   ============================================================================
   WHICH TABLE BACKS WHICH SCREEN
   ============================================================================

   | Screen                    | Reads                                        |
   |---------------------------|----------------------------------------------|
   | Portfolio — who to call   | program_claim + program_engagement           |
   | Location grid             | unit_year_master + unit_month_summary        |
   |                           |   + unit_credit_installment                  |
   | Employees at a location   | onezero_matrix + employee_eligibility        |
   | One employee's payroll    | employee_period_fact + employee_eligibility  |
   | Run status and freshness  | run_manifest                                 |
   | Agent findings            | agent_finding_resolution                     |
   | Claim packages, downloads | artifact (+ artifact_access on download)     |

   Dimension attributes (client name, county, census tract) are NOT duplicated
   here. They live in the source schema and are joined at read time.

   ============================================================================
   PLATFORM NOTES (unchanged from 1.2)
   ============================================================================

   - Fabric Warehouse rejects CREATE INDEX, inline PRIMARY KEY, CHECK, DEFAULT,
     unique indexes, sequences and triggers. Keys are ALTER TABLE ... NOT
     ENFORCED. Section 1a records access patterns; section 9 has the validation
     queries that stand in for the constraints. Run them after every load.
   - Fabric Warehouse uses snapshot isolation and TABLE-level IX locks for DML.
     Two writers to the same table can raise a write-write conflict; the
     application retries. Keep transactions short.
   - Money is DECIMAL(19,4). Never FLOAT, never TEXT.
   - The SQL Server variant (tcc-schema.sqlserver.sql) is GENERATED from this
     file: NOT ENFORCED stripped, section 1a emitted as real indexes.

   ============================================================================
   HOW TO RUN THIS
   ============================================================================

   THIS IS THE BOOTSTRAP: IDEMPOTENT AND DESTRUCTIVE. Every CREATE TABLE is
   preceded by DROP TABLE IF EXISTS; a re-run discards all data. Run it only on
   a fresh Warehouse (no tcc_ops.schema_migration) or an explicitly approved
   rebuild. Later changes are forward-only migrations in
   docs/data/schema/migrations/, recorded in tcc_ops.schema_migration.

   ============================================================================ */


/* ----------------------------------------------------------------------------
   1. SCHEMAS
   ---------------------------------------------------------------------------- */

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'tcc_gold')
    EXEC('CREATE SCHEMA tcc_gold');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'tcc_ops')
    EXEC('CREATE SCHEMA tcc_ops');
GO


/* ----------------------------------------------------------------------------
   1a. ACCESS PATTERNS

   Fabric Warehouse has no CREATE INDEX, so these cannot be declared. They are
   recorded because they are what the tables are actually queried by, and they
   are what to check first if a page is slow — and if this schema is ever moved
   to Fabric SQL Database or SQL Server, they become real indexes.

   | Table                            | Filtered / sorted by                    |
   |----------------------------------|-----------------------------------------|
   | run_manifest                     | client_id, program_code, tax_year,      |
   |                                  |   run_started_at                        |
   | source_snapshot                  | client_id, extracted_at                 |
   | employee_period_fact             | client_id, tax_year, employee_id        |
   | employee_period_fact             | record_token, pay_period_start          |
   | employee_eligibility             | client_id, tax_year, method, employee_id|
   | onezero_matrix                   | client_id, tax_year, method, worksite_id|
   | unit_month_summary               | client_id, tax_year, method, worksite_id|
   | unit_year_master                 | client_id, worksite_id, tax_year        |
   | unit_credit_installment          | client_id, worksite_id, tax_year        |
   | excluded_record                  | client_id, run_id, employee_id          |
   | manual_override                  | client_id, run_id, scope                |
   | exception_report_item            | client_id, run_id, disposition          |
   | rule_pack_version                | program_code, tax_year                  |
   | agent_action_audit               | client_id, occurred_at                  |
   | program_claim                    | client_id, program_code, tax_year,      |
   |                                  |   effective_from                        |
   | program_claim                    | client_id, tax_year                     |
   | program_engagement               | client_id, program_code, effective_from |
   | agent_finding_resolution         | client_id, tax_year, finding_id         |
   | artifact                         | client_id, kind, tax_year, created_at   |
   | artifact                         | container_name, blob_path               |
   | artifact_access                  | client_id, accessed_at                  |
   | client_config                    | client_id, effective_from               |

   The two record_token rows are the drill path: a URL carries a token, and the
   employee page joins employee_period_fact and employee_eligibility on it.
   ---------------------------------------------------------------------------- */


/* ============================================================================
   2. GROUP A — RUN PROVENANCE

   Which source snapshot, which rule version, which code build produced a given
   number. Nothing here can be reconstructed after the fact, which is why it is
   group A rather than an afterthought.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   2.1  run_manifest — one row per calculation run. Immutable once written.

   calculation_id is the reproducibility guarantee: re-running the same snapshot
   under the same assumption set must yield the same hash. If it does not,
   something changed that we failed to version.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.run_manifest;
GO

CREATE TABLE tcc_ops.run_manifest
(
    run_id                      VARCHAR(64)     NOT NULL,
    client_id                   BIGINT          NOT NULL,   -- Account.AccountId
    entity_id                   BIGINT          NULL,       -- Entity.EntityId; NULL = all
    program_code                VARCHAR(32)     NOT NULL,
    tax_year                    INT             NOT NULL,

    -- Per-client, NOT derivable from payroll. Source is
    -- Entity.FiscalYearRulesId -> EntityFiscalYearRules (DDL still outstanding).
    fiscal_year_begin           DATE            NOT NULL,
    fiscal_year_end             DATE            NOT NULL,

    source_snapshot_id          VARCHAR(64)     NULL,       -- FK source_snapshot

    -- Assumptions carry both the label and a content hash. The label alone is
    -- not enough: an edited set under an unchanged id would replay differently.
    step1_assumption_set_id     VARCHAR(64)     NULL,       -- e.g. GDS-STEP1-2026-08-25-v8
    step1_assumption_sha256     CHAR(64)        NULL,
    onezero_assumption_set_id   VARCHAR(64)     NULL,
    onezero_assumption_sha256   CHAR(64)        NULL,

    rule_pack_version           VARCHAR(64)     NULL,       -- statute, versioned separately
    code_commit                 CHAR(40)        NULL,       -- git SHA of the engine
    calculation_id              CHAR(64)        NULL,       -- deterministic hash of inputs+config

    run_started_at              DATETIME2(3)    NOT NULL,
    run_completed_at            DATETIME2(3)    NULL,
    run_status                  VARCHAR(16)     NOT NULL,   -- running | success | failed | superseded
    superseded_by_run_id        VARCHAR(64)     NULL,
    triggered_by                VARCHAR(256)    NULL,       -- user UPN, schedule, agent identity
);
GO

ALTER TABLE tcc_ops.run_manifest
    ADD CONSTRAINT pk_run_manifest PRIMARY KEY NONCLUSTERED (run_id);
GO

/*  CONSTRAINT INTENT
        run_status IN ('running','success','failed','superseded')
        fiscal_year_end > fiscal_year_begin
    triggered_by answers "who ran this calc" from the 4 Sep call.
*/



/* ---------------------------------------------------------------------------
   2.2  source_snapshot — the exact payroll a run consumed.

   Payroll is a moving target: corrections and late files arrive. A run must pin
   the bytes it read, or a figure cannot be reproduced.

   source_max_modify_date is the one that earns its place. Payroll carries
   ModifyDate; recording the highest value observed makes a later correction to
   an already-consumed row DETECTABLE rather than silent.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.source_snapshot;
GO

CREATE TABLE tcc_ops.source_snapshot
(
    snapshot_id              VARCHAR(64)    NOT NULL,
    client_id                BIGINT         NOT NULL,
    extracted_at             DATETIME2(3)   NOT NULL,
    extraction_query_version VARCHAR(64)    NULL,
    row_count                BIGINT         NOT NULL,
    manifest_sha256          CHAR(64)       NULL,

    -- Source-side lineage, from Payroll's own audit columns.
    source_max_modify_date   DATETIME2(3)   NULL,
    source_inload_batch_ids  VARCHAR(4000)  NULL,   -- distinct InloadPayrollId values
);
GO

ALTER TABLE tcc_ops.source_snapshot
    ADD CONSTRAINT pk_source_snapshot PRIMARY KEY NONCLUSTERED (snapshot_id);
GO



/* ---------------------------------------------------------------------------
   2.3  source_file_manifest — one row per file or partition in a snapshot.

   The partner, 20 Aug: "there is a missing pay period in this data, and that does
   happen to us. Sometimes we get a file transmitted that has nothing in it."

   That is exactly why row counts and hashes are recorded PER FILE rather than
   only in aggregate. An empty file in a set of twelve is invisible in a total.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.source_file_manifest;
GO

CREATE TABLE tcc_ops.source_file_manifest
(
    snapshot_id   VARCHAR(64)    NOT NULL,
    ordinal       INT            NOT NULL,
    file_name     VARCHAR(512)   NOT NULL,
    sha256        CHAR(64)       NULL,
    byte_size     BIGINT         NULL,
    row_count     BIGINT         NULL,
    column_list   VARCHAR(8000)  NULL,   -- JSON array
);
GO

ALTER TABLE tcc_ops.source_file_manifest
    ADD CONSTRAINT pk_source_file_manifest PRIMARY KEY NONCLUSTERED (snapshot_id, ordinal);
GO


/* ============================================================================
   3. GROUP B — CALCULATION RESULTS

   The product.

   Volumetrics, one client-year: ~201k + 20k + 20k + 200 + 101 rows. Roughly a
   quarter of a million, dominated by employee_period_fact.

   method is a real dimension, not a variant. The engine computes BOTH methods
   for every client-year and reconciles them; a row without method is ambiguous.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   3.1  employee_period_fact — the normalised denominator grain.

   One row per employee per pay period after the Silver collapse. The only table
   that scales with payroll volume. Partition by client_id, tax_year.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.employee_period_fact;
GO

CREATE TABLE tcc_gold.employee_period_fact
(
    client_id          BIGINT         NOT NULL,
    tax_year           INT            NOT NULL,
    run_id             VARCHAR(64)    NOT NULL,

    employee_id        VARCHAR(64)    NOT NULL,   -- tokenised, never ClientEmployeeID
    record_token       CHAR(24)       NOT NULL,   -- the URL-safe handle; see note
    worksite_id        VARCHAR(64)    NULL,       -- Payroll.WorksiteLocationId (Q3 open)
    entity_fein        VARCHAR(16)    NULL,
    job_title          VARCHAR(128)   NULL,

    pay_period_start   DATE           NOT NULL,
    pay_period_end     DATE           NOT NULL,
    pay_date           DATE           NULL,       -- nullable in source (Q1 open)
    period_days        INT            NOT NULL,   -- inclusive span; drives BA-12
    pay_frequency_code VARCHAR(16)    NULL,       -- lineage only; see BA-03

    hours              DECIMAL(18,2)  NULL,       -- NULL is not 0 (Q2 open)
    wages              DECIMAL(18,2)  NULL,

    pay_code           VARCHAR(64)    NULL,
    included           BIT            NOT NULL,   -- survived the pay-code filter (BA-07)
    selection_decision VARCHAR(32)    NULL,       -- WHY, not just whether
    qc_flag            VARCHAR(32)    NULL        -- NULL | test_of_twos | short_period
);
GO

/*  ON `selection_decision` versus `included`.

    `included` is a boolean and answers "did this row count". That is not enough
    for the employee drill, which has to answer WHY a period did not count —
    outside the fiscal window, shorter than seven days, or filtered out by pay
    code are three different explanations and a reviewer needs to tell them
    apart. Keep both: `included` for filtering, `selection_decision` for the
    explanation on screen.

    ON `pay_frequency_code`. Retained as LINEAGE ONLY and never used as a week
    multiplier. It is `Payroll.PayFrequencyId`, a surrogate key into a lookup
    that has not been supplied; BA-03 measures each period's actual span
    instead. Storing it lets a reviewer see what the source claimed without the
    calculation ever trusting it.

    ON `record_token`. Deterministic — SHA-256 of
    (account_id, program_code, tax_year, employee_id), first 24 hex characters,
    from `tools/tokens.py`. It is stored rather than recomputed so a drill URL
    joins straight to a row, and because it is derived the same way everywhere
    a token minted by one read always resolves in another. Employee IDs may be
    displayed after authentication but must never enter a URL, a log line,
    telemetry or a prompt.
*/

/*  NOTE ON NULL VERSUS ZERO
        Hours and Wages are nullable with DEFAULT 0 in the partner's source. BA-05
        deliberately RETAINS zero-hour rows because a zero-hour wage row is a
        real payroll fact. Whether NULL means the same as 0, or means "not
        reported", is open with the partner (Q2 in the source schema mapping).
        Do not coalesce them away before that is answered.
*/


/* ---------------------------------------------------------------------------
   3.2  employee_eligibility — one row per employee per method per year.

   Persist ALL employees with the eligible flag, not only the passes. The engine
   emits ineligible ones too, and a near-miss is the most interesting row on the
   screen — it is what "who is one lever from qualifying" is built from.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.employee_eligibility;
GO

CREATE TABLE tcc_gold.employee_eligibility
(
    client_id          BIGINT         NOT NULL,
    tax_year           INT            NOT NULL,
    method             VARCHAR(16)    NOT NULL,   -- min_max | pay_period
    run_id             VARCHAR(64)    NOT NULL,

    employee_id        VARCHAR(64)    NOT NULL,
    record_token       CHAR(24)       NOT NULL,   -- the URL-safe handle
    total_hours        DECIMAL(18,2)  NOT NULL,
    total_wages        DECIMAL(18,2)  NOT NULL,

    first_start        DATE           NULL,
    last_end           DATE           NULL,
    days               INT            NULL,
    weeks_worked       DECIMAL(10,2)  NULL,

    -- Rounded half-up to two decimals, and the ROUNDED value is what the
    -- threshold tests (BA-06). Keeping both makes that auditable.
    avg_weekly_hours   DECIMAL(10,2)  NULL,
    avg_weekly_wages   DECIMAL(10,2)  NULL,

    eligible           BIT            NOT NULL,
    weight             DECIMAL(3,2)   NOT NULL    -- 1.00 full-time, pt_weight part-time
);
GO

/*  CONSTRAINT INTENT
        method IN ('min_max','pay_period')
        weight BETWEEN 0 AND 1
*/



/* ---------------------------------------------------------------------------
   3.3  onezero_matrix — one row per eligible employee per unit per method.

   The twelve monthly cells ARE the One/Zero decision. Stored as twelve columns
   rather than an array: BI reads a column as a filterable dimension, and an
   array as an opaque blob.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.onezero_matrix;
GO

CREATE TABLE tcc_gold.onezero_matrix
(
    client_id     BIGINT        NOT NULL,
    tax_year      INT           NOT NULL,
    method        VARCHAR(16)   NOT NULL,
    run_id        VARCHAR(64)   NOT NULL,

    employee_id   VARCHAR(64)   NOT NULL,
    record_token  CHAR(24)      NOT NULL,   -- the URL-safe handle
    worksite_id   VARCHAR(64)   NOT NULL,
    entity_fein   VARCHAR(16)   NULL,

    first_pps     DATE          NOT NULL,
    last_ppe      DATE          NOT NULL,
    weight        DECIMAL(3,2)  NOT NULL,

    month_01      DECIMAL(3,2)  NOT NULL,
    month_02      DECIMAL(3,2)  NOT NULL,
    month_03      DECIMAL(3,2)  NOT NULL,
    month_04      DECIMAL(3,2)  NOT NULL,
    month_05      DECIMAL(3,2)  NOT NULL,
    month_06      DECIMAL(3,2)  NOT NULL,
    month_07      DECIMAL(3,2)  NOT NULL,
    month_08      DECIMAL(3,2)  NOT NULL,
    month_09      DECIMAL(3,2)  NOT NULL,
    month_10      DECIMAL(3,2)  NOT NULL,
    month_11      DECIMAL(3,2)  NOT NULL,
    month_12      DECIMAL(3,2)  NOT NULL
);
GO



/* ---------------------------------------------------------------------------
   3.4  unit_month_summary — per unit, per month, per method.

   average_headcount DIVIDES BY TWELVE ALWAYS, including months that scored
   zero. That matches the partner's own summary output. It is question 24 on the
   outstanding list — the partner's Min-Max summary reports 0 for Month 4 across all 101
   units while the average column still divides by 12 — but until the partner says
   otherwise we divide by 12 to match them.

   Do not "improve" this to divide by months-with-data. It will look more
   correct and it will not tie out.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.unit_month_summary;
GO

CREATE TABLE tcc_gold.unit_month_summary
(
    client_id             BIGINT         NOT NULL,
    tax_year              INT            NOT NULL,
    method                VARCHAR(16)    NOT NULL,
    run_id                VARCHAR(64)    NOT NULL,

    worksite_id           VARCHAR(64)    NOT NULL,

    month_01              DECIMAL(10,2)  NOT NULL,
    month_02              DECIMAL(10,2)  NOT NULL,
    month_03              DECIMAL(10,2)  NOT NULL,
    month_04              DECIMAL(10,2)  NOT NULL,
    month_05              DECIMAL(10,2)  NOT NULL,
    month_06              DECIMAL(10,2)  NOT NULL,
    month_07              DECIMAL(10,2)  NOT NULL,
    month_08              DECIMAL(10,2)  NOT NULL,
    month_09              DECIMAL(10,2)  NOT NULL,
    month_10              DECIMAL(10,2)  NOT NULL,
    month_11              DECIMAL(10,2)  NOT NULL,
    month_12              DECIMAL(10,2)  NOT NULL,

    total                 DECIMAL(12,2)  NOT NULL,
    average_headcount     DECIMAL(10,2)  NOT NULL,   -- total / 12, always
    months_with_headcount INT            NOT NULL,

    -- Month positions no pay period reaches. Added 2 Sep. A structurally empty
    -- month is a fact about the pay calendar, not a location that emptied out,
    -- and the grid hatches these rather than counting them as a decline.
    unreachable_months    VARCHAR(64)    NULL        -- COMMA-SEPARATED month numbers, e.g. '10,11'. NOT JSON.
);
GO



/* ---------------------------------------------------------------------------
   3.45  run_method_summary — one row per client-year-method.

   The One/Zero screen states four things that are properties of the RUN rather
   than of any unit or employee: the annual average, how many employees the
   method found eligible, how many matrix rows it produced, and how many
   employee-months were CONTESTED — the same person at two units in one month,
   resolved by the tie-breaker.

   None of them survived a run. The matrix is deduped before it is written, so
   gold cannot show that a contest happened, and the screen had to re-run the
   engine on every page load to recover a number the run had already known.

   `month_ends` is the twelve measuring dates. They are derivable from the
   fiscal window, but deriving them on read means the window logic runs twice
   and can disagree with itself; the run states what it measured.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.run_method_summary;
GO

CREATE TABLE tcc_gold.run_method_summary
(
    client_id             BIGINT         NOT NULL,
    tax_year              INT            NOT NULL,
    method                VARCHAR(16)    NOT NULL,
    run_id                VARCHAR(64)    NOT NULL,

    program_code          VARCHAR(32)    NOT NULL,

    annual_average        DECIMAL(12,2)  NOT NULL,
    eligible_employees    INT            NOT NULL,
    employees_evaluated   INT            NOT NULL,
    matrix_rows           INT            NOT NULL,
    unit_fein_rows        INT            NOT NULL,

    -- Employee-months where one person appeared at more than one unit. The
    -- tie-breaker has already resolved them; this is the record of what it had
    -- to decide, not an outstanding queue.
    contested_months      INT            NOT NULL,

    -- The twelve measuring dates, as the run measured them. JSON array of ISO
    -- dates, e.g. '["2023-08-31", ...]'.
    month_ends            VARCHAR(256)   NOT NULL,

    appended_at           DATETIME2(6)   NOT NULL
);
GO



/* ---------------------------------------------------------------------------
   3.5  unit_year_master — cross-year, per unit. The partner's own pattern, productised.

   The partner: "Once I've done the 1/0 with each employee, I then collapse it and sum
   by unit number, and then I store it to a master table. So I've got the
   history of 2025, 2024, 2023. It's run append, run append, run append."

   Not a convenience view — a REQUIREMENT. Georgia credits compare a year to a
   base year, and the partner wants five years plus a sixth as baseline.

   THIS IS THE PRIMARY READ TABLE. The per-location grid — the screen an
   operator opens the portal on — is one query against this table plus
   unit_month_summary. Everything from `average_headcount` down to
   `annual_credit_usd` is written by a run and read directly; nothing on that
   screen is computed at display time.

   is_current handles restatement: a re-run supersedes rather than overwrites,
   so a prior year's filed figure stays readable exactly as filed.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.unit_year_master;
GO

CREATE TABLE tcc_gold.unit_year_master
(
    client_id              BIGINT         NOT NULL,
    worksite_id            VARCHAR(64)    NOT NULL,
    entity_fein            VARCHAR(16)    NULL,
    program_code           VARCHAR(32)    NOT NULL,
    method                 VARCHAR(16)    NOT NULL,   -- min_max | pay_period
    tax_year               INT            NOT NULL,

    -- Headcount
    average_headcount      DECIMAL(10,2)  NOT NULL,
    is_base_year           BIT            NOT NULL,
    base_average_headcount DECIMAL(10,2)  NULL,       -- the frozen baseline
    base_year_source       VARCHAR(16)    NULL,       -- inferred | override
    net_new_vs_base        DECIMAL(10,2)  NULL,

    -- Year completeness. Added 2 Sep, from the partner's feedback. A year is complete
    -- when it fills every REACHABLE month, not all twelve: a calendar-year
    -- client has no December measuring date, so eleven months is its complete
    -- year. Judging against twelve rejected it as a base year and pushed the
    -- base a year later — which moved the reference portfolio claim from
    -- 229,285 to 607,110.
    --
    -- THE DIVISOR STAYS 12 (see unit_month_summary). Only completeness changed.
    months_reachable       INT            NULL,
    year_complete          BIT            NULL,
    declined               BIT            NOT NULL,   -- under half the targets reachable
    decline_reason         VARCHAR(512)   NULL,

    -- Qualification. The threshold is the statutory minimum new jobs; it comes
    -- from a negotiated designation where one exists, otherwise from the rule
    -- pack, and which of those applied has to be readable years later.
    threshold              DECIMAL(10,2)  NULL,
    threshold_source       VARCHAR(16)    NULL,       -- designation | rule_pack
    qualified              BIT            NOT NULL,
    status                 VARCHAR(16)    NOT NULL,   -- see domain below

    -- Geographic tier. Prototype data covering four worksites at present;
    -- unregistered units fall back to the rule pack's minimum and are marked
    -- `unassigned` rather than silently defaulted to Tier 1.
    tier                   VARCHAR(32)    NULL,
    designation            VARCHAR(64)    NULL,
    tier_source            VARCHAR(16)    NULL,       -- prototype | unassigned

    -- The stair-step. `high_water_mark` is the running maximum average seen
    -- through this year and never drops below the base, which is what stops a
    -- recovery being counted as fresh job creation. `backfilled` marks a year
    -- that re-qualified after a non-qualifying one.
    --
    -- eligible_jobs and new_jobs_created are NOT the same number and must both
    -- be stored. `eligible_jobs` is net-new above the FROZEN BASE and sizes the
    -- annual credit. `new_jobs_created` is the increment above the RUNNING
    -- HIGH-WATER MARK and sizes a new tranche. In a recovery year the first is
    -- positive while the second is zero — the jobs are claimable but they are
    -- not fresh creation, so no new tranche opens. Storing only one makes that
    -- distinction unrecoverable.
    eligible_jobs          DECIMAL(10,2)  NULL,       -- net_new if qualified, else 0
    new_jobs_created       DECIMAL(10,2)  NULL,       -- above high-water; opens a tranche
    high_water_mark        DECIMAL(10,2)  NULL,
    backfilled             BIT            NOT NULL,

    -- The rule-pack parameters AS APPLIED, not as they read today. A statute
    -- amended between the run and the audit must not silently restate a filed
    -- figure, so the dollars-per-job and benefit window are copied onto the row
    -- that used them. annual_credit_usd = eligible_jobs x per_job_usd, and with
    -- both factors present the arithmetic is checkable from the row alone.
    per_job_usd            DECIMAL(19,4)  NULL,
    tranche_years          INT            NULL,       -- benefit window (GA = 5)
    annual_credit_usd      DECIMAL(19,4)  NULL,

    -- Human intervention. The override itself lives in tcc_ops.manual_override;
    -- these flags exist so a screen can mark the figure as adjusted without
    -- joining out to find that nothing was adjusted.
    base_year_overridden   BIT            NOT NULL,
    high_water_mark_overridden BIT        NOT NULL,

    run_id                 VARCHAR(64)    NOT NULL,
    is_current             BIT            NOT NULL,
    appended_at            DATETIME2(3)   NOT NULL
);
GO

/*  CONSTRAINT INTENT
        method           IN ('min_max','pay_period')
        base_year_source IN ('inferred','override')
        threshold_source IN ('designation','rule_pack')
        tier_source      IN ('prototype','unassigned')
        status           IN ('base','above_minimum','below_minimum',
                             'partial','no_data',
                             'before_base','in_progress')

    ON `status`. These readings are decided in one place
    (`tools/unit_trend.unit_status`) and must not be re-derived downstream.
    `partial` means the client's payroll does not cover the year. A month whose
    measuring date no pay period reaches is a DIFFERENT fact — the year is
    complete and the calendar is the problem — and reporting that as a short
    year would be wrong. `no_data` is neither: it is a unit with no headcount at
    all in that year.

    UNIQUE INDEX INTENT — one current row per unit-year-method.
        (client_id, worksite_id, program_code, method, tax_year)
        WHERE is_current = 1
    Verify with query 9.4.
*/



/* ---------------------------------------------------------------------------
   3.6  unit_credit_installment — the tranche projection, at its atomic grain

   Each qualifying year opens its own credit window, and a window pays an
   installment in each of the following years. A given tax year's claimable
   figure is therefore the SUM of every live window's installment for it, which
   is why this cannot be a column on unit_year_master: the grain is different.
   One qualifying year in 2021 contributes to 2021 through 2026.

   GRAIN: creation_year x claimable_year, not claimable_year alone.

   The screen wants one number per claimable year, which is tempting to store
   directly with a list of contributing creation years alongside it. Don't. That
   shape puts a multi-valued fact in one column, and it discards the per-window
   arithmetic — you keep the total but lose which window paid what, so a figure
   that looks wrong cannot be taken apart. The atomic row costs a GROUP BY on
   read and keeps the trace:

       SELECT tax_year, SUM(claimable_usd)
       FROM tcc_gold.unit_credit_installment
       WHERE is_current = 1 AND client_id = ? AND worksite_id = ? AND method = ?
       GROUP BY tax_year;

   `jobs_maintained` is the driver and must be stored beside the dollar. A job
   is claimable in an out-year only if that year's average headcount still sits
   above the frozen base by at least the tranche size; where it doesn't, the
   installment is written down. Without this column a reduced installment is
   indistinguishable from a rule change.

   `projected` is load-bearing. An installment in a year with NO PAYROLL YET is
   a FORECAST on the carry-forward assumption that the job is maintained, not a
   claim. That is a different statement from a measured installment that
   happens to equal the full tranche, and the two must not render alike.
   Reported as `claimable_usd` rather than `credit` for the same reason.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_gold.unit_credit_installment;
GO

CREATE TABLE tcc_gold.unit_credit_installment
(
    client_id           BIGINT         NOT NULL,
    worksite_id         VARCHAR(64)    NOT NULL,
    program_code        VARCHAR(32)    NOT NULL,
    method              VARCHAR(16)    NOT NULL,

    creation_year       INT            NOT NULL,   -- the year that opened the window
    tax_year            INT            NOT NULL,   -- the year the installment falls in

    tranche_jobs        DECIMAL(10,2)  NOT NULL,   -- window size at creation
    jobs_maintained     DECIMAL(10,2)  NOT NULL,   -- still above base this year
    per_job_usd         DECIMAL(19,4)  NOT NULL,   -- rule pack AS APPLIED
    claimable_usd       DECIMAL(19,4)  NOT NULL,   -- jobs_maintained x per_job_usd
    projected           BIT            NOT NULL,   -- no payroll yet; carry-forward

    run_id              VARCHAR(64)    NOT NULL,
    is_current          BIT            NOT NULL,
    appended_at         DATETIME2(3)   NOT NULL
);
GO

/*  CONSTRAINT INTENT — Fabric Warehouse will not enforce these.
        UNIQUE (client_id, worksite_id, program_code, method,
                creation_year, tax_year) WHERE is_current = 1
        CHECK  tax_year >= creation_year
        CHECK  jobs_maintained <= tranche_jobs
        CHECK  claimable_usd = ROUND(jobs_maintained * per_job_usd, 0)
    Verify with queries 9.4b and 9.4c.
*/



/* ============================================================================
   4. GROUP C — EXCLUSIONS AND OVERRIDES

   The group the partner asked for most insistently.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   4.1  excluded_record — soft delete

   The partner: "Maybe you capture the ineligibles and then give the user the ability
   to review the ineligibles and say, well, wait a minute, that one should be
   eligible. Let's put it back over there."

   numerator_treatment is not decoration. Under BA-12 the hours and wages of an
   excluded period STILL COUNT toward the numerator; only the denominator loses
   it. Anyone reading this table later needs to know that without reading code.

   Sizing from the reference run: 1,705 excluded rows carrying 7,726.49 hours
   and $1,859,776.29, touching 998 employees, of whom 156 are left with no valid
   pay period at all.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.excluded_record;
GO

CREATE TABLE tcc_ops.excluded_record
(
    exclusion_id        VARCHAR(64)    NOT NULL,
    run_id              VARCHAR(64)    NOT NULL,
    client_id           BIGINT         NOT NULL,
    employee_id         VARCHAR(64)    NOT NULL,

    pay_period_start    DATE           NOT NULL,
    pay_period_end      DATE           NOT NULL,
    period_days         INT            NOT NULL,
    hours               DECIMAL(18,2)  NULL,
    wages               DECIMAL(18,2)  NULL,

    exclusion_rule      VARCHAR(64)    NOT NULL,   -- e.g. BA-12_short_pay_period
    numerator_treatment VARCHAR(16)    NOT NULL,   -- retained | removed
    source_refs         VARCHAR(4000)  NULL,       -- JSON: file + row number

    is_reinstated       BIT            NOT NULL,
    reinstated_by       VARCHAR(256)   NULL,
    reinstated_at       DATETIME2(3)   NULL,
    reinstatement_note  VARCHAR(2000)  NULL
);
GO

ALTER TABLE tcc_ops.excluded_record
    ADD CONSTRAINT pk_excluded_record PRIMARY KEY NONCLUSTERED (exclusion_id);
GO

/*  CONSTRAINT INTENT
        numerator_treatment IN ('retained','removed')
        is_reinstated = 0 OR (reinstated_by IS NOT NULL AND reinstated_at IS NOT NULL)
*/



/* ---------------------------------------------------------------------------
   4.2  manual_override

   The partner: "We should have that manual adjustment function where we can shove them
   from one side to the other."

   This is the table that answers "capture if people make adjustments" from the
   4 Sep call.

   Overrides are ADDITIVE, never destructive. The engine output stays exactly as
   computed and the override is a separate layer applied on top, so the machine
   result and the human result are both always visible. For a filed return you
   need to be able to show both.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.manual_override;
GO

CREATE TABLE tcc_ops.manual_override
(
    override_id        VARCHAR(64)    NOT NULL,
    run_id             VARCHAR(64)    NOT NULL,
    client_id          BIGINT         NOT NULL,

    scope              VARCHAR(16)    NOT NULL,   -- employee | record | unit
    target_key         VARCHAR(256)   NOT NULL,
    field_changed      VARCHAR(128)   NOT NULL,
    value_before       VARCHAR(512)   NULL,
    value_after        VARCHAR(512)   NULL,

    reason_code        VARCHAR(64)    NULL,
    justification_text VARCHAR(2000)  NULL,

    created_by         VARCHAR(256)   NOT NULL,
    created_at         DATETIME2(3)   NOT NULL,
    approved_by        VARCHAR(256)   NULL,
    approved_at        DATETIME2(3)   NULL
);
GO

ALTER TABLE tcc_ops.manual_override
    ADD CONSTRAINT pk_manual_override PRIMARY KEY NONCLUSTERED (override_id);
GO

/*  CONSTRAINT INTENT
        scope IN ('employee','record','unit')
*/



/* ---------------------------------------------------------------------------
   4.3  exception_report_item

   The partner: "We should have some sort of an exception report or some sort of an
   analytical report that says, yes, this client had this weird thing going on."

   Seed the catalogue with what the engine already detects: missing pay periods
   in a cadence, denominators above 52/53 weeks, Pay Period weeks exceeding
   Min-Max weeks, test-of-twos overlaps, abnormal period lengths (the 13- and
   15-day cases the partner flagged but we chose not to exclude automatically), and
   unmapped pay codes.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.exception_report_item;
GO

CREATE TABLE tcc_ops.exception_report_item
(
    item_id           VARCHAR(64)    NOT NULL,
    run_id            VARCHAR(64)    NOT NULL,
    client_id         BIGINT         NOT NULL,

    severity          VARCHAR(16)    NOT NULL,   -- info | warning | error
    rule_code         VARCHAR(64)    NOT NULL,
    entity_type       VARCHAR(32)    NOT NULL,   -- employee | unit | period | pay_code
    entity_key        VARCHAR(256)   NOT NULL,
    message           VARCHAR(2000)  NOT NULL,

    disposition       VARCHAR(16)    NOT NULL,   -- open | accepted | corrected
    dispositioned_by  VARCHAR(256)   NULL,
    dispositioned_at  DATETIME2(3)   NULL
);
GO

ALTER TABLE tcc_ops.exception_report_item
    ADD CONSTRAINT pk_exception_item PRIMARY KEY NONCLUSTERED (item_id);
GO

/*  CONSTRAINT INTENT
        severity    IN ('info','warning','error')
        disposition IN ('open','accepted','corrected')
        disposition = 'open' OR dispositioned_by IS NOT NULL
*/



/* ============================================================================
   5. GROUPS D AND E — RULE HISTORY AND ACTIVITY

   What the rules were on the day the return was filed, and who or what changed
   something. Both are audit substrate: cheap to write, impossible to
   reconstruct.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   5.1  assumption_set_version — immutable, replayable.

   We already run this discipline in the repo: v1 through v8, each retained and
   replayable. It needs to survive the move into the partner's estate rather than
   being flattened to "current rules".
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.assumption_set_version;
GO

CREATE TABLE tcc_ops.assumption_set_version
(
    assumption_set_id VARCHAR(64)    NOT NULL,
    schema_version    VARCHAR(16)    NOT NULL,
    status            VARCHAR(16)    NOT NULL,   -- draft | active | superseded
    supersedes        VARCHAR(64)    NULL,
    content_json      VARCHAR(8000)  NOT NULL,   -- the set itself; VARCHAR(MAX) if available
    sha256            CHAR(64)       NOT NULL,
    authored_by       VARCHAR(256)   NULL,
    approved_by       VARCHAR(256)   NULL,
    approved_at       DATETIME2(3)   NULL,
    effective_from    DATE           NOT NULL,
    effective_to      DATE           NULL
);
GO

ALTER TABLE tcc_ops.assumption_set_version
    ADD CONSTRAINT pk_assumption_set PRIMARY KEY NONCLUSTERED (assumption_set_id);
GO


/* ---------------------------------------------------------------------------
   5.2  rule_pack_version — the STATUTE, versioned by year.

   Kept apart from assumption sets deliberately. A rule pack is a fact about
   what the law said in a given tax year; an assumption set is a choice we made
   about how to read an ambiguous instruction. Conflating them makes it
   impossible to answer "did the law change, or did we?".
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.rule_pack_version;
GO

CREATE TABLE tcc_ops.rule_pack_version
(
    rule_pack_version VARCHAR(64)    NOT NULL,
    program_code      VARCHAR(32)    NOT NULL,
    tax_year          INT            NOT NULL,
    content_json      VARCHAR(8000)  NOT NULL,
    sha256            CHAR(64)       NOT NULL,
    citation          VARCHAR(512)   NULL,       -- e.g. O.C.G.A. 48-7-40
    source_url        VARCHAR(1024)  NULL,
    authored_by       VARCHAR(256)   NULL,
    approved_by       VARCHAR(256)   NULL,
    approved_at       DATETIME2(3)   NULL,
    effective_from    DATE           NOT NULL,
    effective_to      DATE           NULL
);
GO

ALTER TABLE tcc_ops.rule_pack_version
    ADD CONSTRAINT pk_rule_pack PRIMARY KEY NONCLUSTERED (rule_pack_version);
GO



/* ---------------------------------------------------------------------------
   5.3  rule_change_audit

   Shashi, verbatim: "When somebody changes the rule in the Flex app, we need to
   know that."

   source_citation is the field that would have carried "the partner,
   2026-08-20 call" for the change we made on 2 September. Without it, in
   eighteen months nobody knows why the completeness rule flipped — only that it
   did, and that a published figure moved from 229,285 to 607,110.

   runs_invalidated matters just as much: changing a rule retrospectively
   invalidates every run that used the old one, and those runs may already be
   cited on a filed return.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.rule_change_audit;
GO

CREATE TABLE tcc_ops.rule_change_audit
(
    change_id                 VARCHAR(64)    NOT NULL,
    assumption_set_id_before  VARCHAR(64)    NULL,
    assumption_set_id_after   VARCHAR(64)    NULL,
    assumption_code           VARCHAR(32)    NULL,       -- e.g. BA-12
    field_path                VARCHAR(256)   NULL,
    value_before              VARCHAR(512)   NULL,
    value_after               VARCHAR(512)   NULL,
    rationale                 VARCHAR(2000)  NULL,
    source_citation           VARCHAR(512)   NULL,       -- who said so, and when
    changed_by                VARCHAR(256)   NOT NULL,
    changed_at                DATETIME2(3)   NOT NULL,
    runs_invalidated          VARCHAR(8000)  NULL,       -- JSON array of run_id
);
GO

ALTER TABLE tcc_ops.rule_change_audit
    ADD CONSTRAINT pk_rule_change PRIMARY KEY NONCLUSTERED (change_id);
GO


/* ---------------------------------------------------------------------------
   5.4  agent_action_audit

   Shashi: "When somebody runs an agent and changes something, we need to
   capture that." And on the 4 Sep call: "any kind of agent observability".

   is_deterministic_path is the load-bearing column. The architecture holds that
   AGENTS NARRATE AND TOOLS CALCULATE — this column is the evidence that no
   number on a return came from a model. It should be true for every row that
   touches a figure, and a false one is a finding.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.agent_action_audit;
GO

CREATE TABLE tcc_ops.agent_action_audit
(
    action_id             VARCHAR(64)    NOT NULL,
    run_id                VARCHAR(64)    NULL,
    client_id             BIGINT         NULL,

    agent_name            VARCHAR(128)   NOT NULL,
    agent_version         VARCHAR(32)    NULL,
    model_deployment      VARCHAR(128)   NULL,
    prompt_hash           CHAR(64)       NULL,
    tool_calls            VARCHAR(8000)  NULL,       -- JSON
    input_summary         VARCHAR(2000)  NULL,
    output_summary        VARCHAR(2000)  NULL,

    user_upn              VARCHAR(256)   NULL,
    occurred_at           DATETIME2(3)   NOT NULL,
    is_deterministic_path BIT            NOT NULL
);
GO

ALTER TABLE tcc_ops.agent_action_audit
    ADD CONSTRAINT pk_agent_action PRIMARY KEY NONCLUSTERED (action_id);
GO



/* ============================================================================
   6. GROUP F — CLAIMS AND COVERAGE

   The commercial record: what we identified, what the client claimed, and what
   the authority certified.

   All three are APPEND-ONLY. A change INSERTS a new row and closes the prior one
   by stamping effective_to / superseded_at. Nothing is updated in place except
   that closing stamp, because the question an audit asks is "what did you
   believe on the day you filed?" and an overwritten row cannot answer it.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   6.1  program_claim — grain is client x program x tax year.

   One row per cell of the coverage matrix. The live row is effective_to IS NULL.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.program_claim;
GO

CREATE TABLE tcc_ops.program_claim
(
    claim_id                VARCHAR(64)     NOT NULL,
    client_id               BIGINT          NOT NULL,
    entity_id               BIGINT          NULL,
    program_code            VARCHAR(32)     NOT NULL,
    tax_year                INT             NOT NULL,

    status                  VARCHAR(24)     NOT NULL,
    provenance              VARCHAR(32)     NOT NULL,

    identified_usd          DECIMAL(19,4)   NOT NULL,   -- engine computed as available
    claimed_usd             DECIMAL(19,4)   NOT NULL,   -- actually claimed
    certified_usd           DECIMAL(19,4)   NOT NULL,   -- authority approved

    -- The jobs reasoning behind identified_usd. FLOAT is correct: a headcount
    -- average is a measurement, and nothing sums it into a filed figure.
    average_headcount       FLOAT           NULL,
    base_average_headcount  FLOAT           NULL,
    threshold_jobs          FLOAT           NULL,

    -- The earliest year held. Net-new needs a prior year, so this cell's
    -- identified figure is zero by construction and cannot be compared with a
    -- filed amount. See domain.claims.Outcome.BASE_YEAR.            (NEW 2.0)
    is_base_year            BIT             NOT NULL,

    identified_run_id       VARCHAR(64)     NULL,       -- FK run_manifest
    assumption_set_id       VARCHAR(64)     NULL,
    rule_pack_version       VARCHAR(64)     NULL,

    filed_on                DATE            NULL,
    filing_reference        VARCHAR(128)    NULL,

    decided_by              VARCHAR(256)    NULL,
    decided_at              DATETIME2(3)    NULL,
    decline_reason          VARCHAR(1024)   NULL,

    effective_from          DATE            NOT NULL,
    effective_to            DATE            NULL
);
GO

ALTER TABLE tcc_ops.program_claim
    ADD CONSTRAINT pk_program_claim PRIMARY KEY NONCLUSTERED (claim_id);
GO

/*  CONSTRAINT INTENT — enforced in SQLite, not enforceable in Fabric Warehouse.

    status IN ('not_assessed','assessed','proposed','declined',
               'claimed','certified','amended')

    provenance IN ('computed','filed_by_us','client_asserted',
                   'inherited','authority_confirmed')

    status <> 'declined' OR (decline_reason IS NOT NULL AND
                             LTRIM(RTRIM(decline_reason)) <> '')

    Lifecycle:
        not_assessed -> assessed -> proposed -+-> claimed -> certified
                                              |                |
                                              +-> declined     +-> amended

    WHY 'declined' NEEDS A REASON. A client saying "we're not claiming WOTC, we
    take the R&D credit instead" is durable knowledge. Without it every
    subsequent run re-proposes the same thing and the consultant looks like they
    are not listening.

    WHY provenance EXISTS. 'client_asserted' and 'inherited' are UNVERIFIED —
    they rest on somebody's word. An unverified assertion and a certified filing
    look identical as a dollar figure, and treating them alike is how a number
    nobody stands behind reaches a return.
*/

/*  NOT A MISSING COLUMN — the coverage outcome is DERIVED, never stored.

    The domain has an Outcome enum (not_assessed, correctly_not_claimed,
    unclaimed, confirmed, under_claimed, over_claimed, out_of_scope) that drives
    the coverage matrix. It is a comparison of identified_usd against
    claimed_usd, computed at read time — so there is deliberately no column.

    | Claimed | Computed | Outcome              | Meaning              |
    |---------|----------|----------------------|----------------------|
    | $0      | $0       | correctly_not_claimed| nothing to do        |
    | $0      | $Y       | unclaimed            | new opportunity      |
    | $X      | ~$X      | confirmed            | reassurance          |
    | $X      | $Y > X   | under_claimed        | RECOVERABLE          |
    | $X      | $Y < X   | over_claimed         | EXPOSURE             |

    Storing it would let the stored value drift from the two figures it derives
    from, and the cell that matters most is over_claimed. Derive it in the
    pipeline the same way; do not persist it.
*/



/*  UNIQUE INDEX INTENT — not expressible in Fabric Warehouse.
        (client_id, program_code, tax_year) WHERE effective_to IS NULL
    Without it a double-write leaves two "current" rows and the coverage matrix
    silently double-counts a claim. Verify with query 9.1.
*/


/* ---------------------------------------------------------------------------
   6.2  program_engagement — are we engaged to handle this program at all?

   Without it the coverage matrix cannot tell "unclaimed — an opportunity" from
   "unclaimed — not our mandate". Both render as a gap, and one is noise that
   erodes trust in the other.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.program_engagement;
GO

CREATE TABLE tcc_ops.program_engagement
(
    client_id       BIGINT          NOT NULL,
    program_code    VARCHAR(32)     NOT NULL,
    scope           VARCHAR(24)     NOT NULL,   -- in_scope | out_of_scope | prospective
    effective_from  DATE            NOT NULL,
    effective_to    DATE            NULL,
    note            VARCHAR(1024)   NULL
);
GO

/*  CONSTRAINT INTENT
        scope IN ('in_scope','out_of_scope','prospective')
    UNIQUE: one live engagement per (client_id, program_code). Query 9.2.
*/



/* ---------------------------------------------------------------------------
   6.3  agent_finding_resolution — a human's answer to something an agent found.

   Reopening writes a NEW row and stamps superseded_at on the prior one. A
   resolution that changes a filed figure has to survive a container recycle.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.agent_finding_resolution;
GO

CREATE TABLE tcc_ops.agent_finding_resolution
(
    finding_id      VARCHAR(128)    NOT NULL,
    client_id       BIGINT          NOT NULL,
    tax_year        INT             NOT NULL,
    resolution      VARCHAR(16)     NOT NULL,   -- accept | assign | drop | flag
    detail          VARCHAR(1024)   NULL,
    note            VARCHAR(4000)   NULL,
    decided_by      VARCHAR(256)    NOT NULL,
    decided_at      DATETIME2(3)    NOT NULL,
    superseded_at   DATETIME2(3)    NULL        -- NULL = the live decision
);
GO

/*  CONSTRAINT INTENT
        resolution IN ('accept','assign','drop','flag')
    UNIQUE: one live resolution per (client_id, finding_id). Query 9.3.
    A second would make "what did we decide?" ambiguous at the moment it
    matters most.
*/



/* ============================================================================
   6A. GROUP G — ARTIFACTS                                          (NEW 2.0)

   Blob Storage holds two kinds of file:
     rule_source    source documents a rule pack was authored from (statute
                    text, agency guidance). Rule packs themselves stay in Git.
     claim_package  generated outputs for a client (PDF / XLSX / CSV).

   Nothing outside the application reaches the storage account: public network
   access off, shared keys off, no anonymous access, no SAS handed to a browser.
   The API authorizes the user for the client, looks the artifact up HERE, then
   streams the blob. That makes this table the authorization record, not a
   convenience index — a blob with no row is unreachable by design.
   ============================================================================ */

/* ---------------------------------------------------------------------------
   6A.1  artifact — one blob.

   Append-only like the rest of tcc_ops: regenerating a package writes a new
   artifact and stamps superseded_at on the prior one. The blob itself is
   immutable (versioning on); blob_path is never reused.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.artifact;
GO

CREATE TABLE tcc_ops.artifact
(
    artifact_id         VARCHAR(64)     NOT NULL,
    kind                VARCHAR(24)     NOT NULL,   -- rule_source | claim_package
    client_id           BIGINT          NULL,       -- NULL only for rule_source
    program_code        VARCHAR(32)     NULL,
    tax_year            INT             NULL,
    run_id              VARCHAR(64)     NULL,       -- FK run_manifest (claim_package)
    rule_pack_version   VARCHAR(64)     NULL,       -- FK rule_pack_version (rule_source)

    container_name      VARCHAR(63)     NOT NULL,   -- artifacts | outputs
    blob_path           VARCHAR(1024)   NOT NULL,   -- outputs: {client_id}/{run_id}/{file}
    file_name           VARCHAR(256)    NOT NULL,
    content_type        VARCHAR(128)    NOT NULL,
    size_bytes          BIGINT          NOT NULL,
    sha256              CHAR(64)        NOT NULL,

    created_by          VARCHAR(256)    NOT NULL,   -- user UPN or 'system:<job>'
    created_at          DATETIME2(3)    NOT NULL,
    retain_until        DATE            NULL,       -- mirrors the lifecycle policy
    superseded_at       DATETIME2(3)    NULL        -- NULL = the live artifact
);
GO

ALTER TABLE tcc_ops.artifact
    ADD CONSTRAINT pk_artifact PRIMARY KEY NONCLUSTERED (artifact_id);
GO

/*  CONSTRAINT INTENT
        kind IN ('rule_source','claim_package')
        kind = 'claim_package' => client_id IS NOT NULL AND run_id IS NOT NULL
        container_name = 'outputs' => blob_path LIKE CAST(client_id AS VARCHAR) + '/%'
    UNIQUE: blob_path per container_name. Queries 9.10 and 9.11.

    WHY THE PATH CARRIES client_id. Defence in depth: even if an authorization
    check were skipped, a path built from the requesting tenant cannot resolve
    another tenant's file.
*/


/* ---------------------------------------------------------------------------
   6A.2  artifact_access — one download.

   Claim packages contain taxpayer data. Who took a copy, and when, is an audit
   question with a short answer only if it was written down at the time.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.artifact_access;
GO

CREATE TABLE tcc_ops.artifact_access
(
    access_id           VARCHAR(64)     NOT NULL,
    artifact_id         VARCHAR(64)     NOT NULL,   -- FK artifact
    client_id           BIGINT          NULL,       -- denormalised: tenant leads every query
    user_upn            VARCHAR(256)    NOT NULL,
    user_oid            VARCHAR(64)     NULL,       -- Entra object id
    accessed_at         DATETIME2(3)    NOT NULL,
    outcome             VARCHAR(16)     NOT NULL    -- served | denied | missing
);
GO

ALTER TABLE tcc_ops.artifact_access
    ADD CONSTRAINT pk_artifact_access PRIMARY KEY NONCLUSTERED (access_id);
GO

/*  CONSTRAINT INTENT
        outcome IN ('served','denied','missing')
    Denials are recorded too: a pattern of denied requests is the signal.
*/



/* ---------------------------------------------------------------------------
   6A.3  schema_migration — which schema changes this Warehouse has applied. (NEW 2.0)

   THIS FILE IS THE BOOTSTRAP, AND IT IS DESTRUCTIVE. Run it only on a Warehouse
   that has no tcc_ops.schema_migration table (a fresh one), or on a Warehouse
   item explicitly approved for a rebuild. Every later change is a forward-only
   migration in docs/data/schema/migrations/NNNN_<slug>.sql, recorded here.
   Post-provision automation applies pending migrations; it never re-runs this.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.schema_migration;
GO

CREATE TABLE tcc_ops.schema_migration
(
    version         VARCHAR(16)     NOT NULL,   -- e.g. 0000, 0001
    name            VARCHAR(128)    NOT NULL,
    sha256          CHAR(64)        NOT NULL,   -- of the migration file as applied
    applied_at      DATETIME2(3)    NOT NULL,
    applied_by      VARCHAR(256)    NOT NULL
);
GO

ALTER TABLE tcc_ops.schema_migration
    ADD CONSTRAINT pk_schema_migration PRIMARY KEY NONCLUSTERED (version);
GO

INSERT INTO tcc_ops.schema_migration (version, name, sha256, applied_at, applied_by)
VALUES ('0000', 'bootstrap_v2.0', REPLICATE('0', 64), SYSUTCDATETIME(), SUSER_SNAME());
GO


/* ============================================================================
   7. CLIENT CONFIGURATION
   ============================================================================ */

/* ---------------------------------------------------------------------------
   7.1  client_config

   THIS TABLE MAY ALREADY EXIST ON THE PARTNER'S SIDE. Entity carries
   FiscalYearRulesId -> EntityFiscalYearRules, which is presumably the "this is
   the client, this is the fiscal year" table the partner described. We need that DDL
   (Q4). If it expresses rules like "the Saturday nearest 31 July", this table
   should REFERENCE it rather than duplicate it — a second copy of a fiscal-year
   rule is a second thing to get out of step.

   Note the grain difference: FiscalYearRulesId hangs off Entity, not Account. A
   client with several legal entities could in principle have different fiscal
   years per entity, which the reference dataset's single 53-week window would
   not have revealed. Worth confirming.

   The partner: "We'll have to build you a table with 'this is the client, this is the
   fiscal year'... we can't just run it across every client and say, oh, they're
   all calendar year."

   Today the partner's team hand-edits the dates at the top of a query. That is the
   fragility this table removes.
   --------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tcc_ops.client_config;
GO

CREATE TABLE tcc_ops.client_config
(
    client_id               BIGINT         NOT NULL,
    entity_id               BIGINT         NULL,       -- grain may be per entity, not per account
    fiscal_year_begin_rule  VARCHAR(256)   NULL,       -- literal date or rule expression
    fiscal_year_end_rule    VARCHAR(256)   NULL,
    fiscal_year_rules_id    BIGINT         NULL,       -- FK to the partner's EntityFiscalYearRules
    is_staffing_client      BIT            NOT NULL,
    programs_enrolled       VARCHAR(1024)  NULL,       -- JSON array of program_code
    effective_from          DATE           NOT NULL,
    effective_to            DATE           NULL
);
GO

/*  is_staffing_client drives a SECOND DATA PATH. Staffing payroll carries a
    branch ID that does not indicate where the employee actually worked, so
    those clients supply a separate worksite file. Likely maps to
    Account.IndustryTypeId or AccountTypeId.
*/



/* ============================================================================
   8. TYPE MAPPING AND CONVENTIONS
   ============================================================================

   | Concept              | Type          | Why                                |
   |----------------------|---------------|------------------------------------|
   | tenant               | BIGINT        | Account.AccountId                  |
   | money                | DECIMAL(19,4) | exact; never FLOAT, never TEXT     |
   | headcount / averages | FLOAT or      | measurement, not money             |
   |                      | DECIMAL(10,2) |                                    |
   | weeks, weekly avgs   | DECIMAL(10,2) | rounded half-up, and the ROUNDED   |
   |                      |               | value is what BA-06 tests          |
   | One/Zero cells       | DECIMAL(3,2)  | 1.00 / 0.00 / part-time weight     |
   | dates                | DATE          | fiscal dates, no time component    |
   | instants             | DATETIME2(3)  | audit timestamps, UTC              |
   | hashes               | CHAR(64)      | SHA-256 hex                        |
   | git commit           | CHAR(40)      | SHA-1 hex                          |
   | JSON                 | VARCHAR(8000) | use VARCHAR(MAX) where supported   |
   | booleans             | BIT           |                                    |

   Fabric Warehouse has no NVARCHAR — VARCHAR carries UTF-8 under the default
   Latin1_General_100_BIN2_UTF8 collation.

   NAMING. snake_case throughout, matching the application and the documents.
   client_id is the tenant key everywhere and leads every index, because tenant
   leads every query.

   ============================================================================
   9. VALIDATION

   Fabric Warehouse cannot enforce the constraints this model depends on, so
   these are not optional. Run after every load. Each returns zero rows when
   healthy. A violation does not raise an error — it silently corrupts a total.
   ============================================================================ */

-- 9.1  More than one live claim per cell. Double-counts in the coverage matrix.
SELECT client_id, program_code, tax_year, COUNT(*) AS live_rows
FROM tcc_ops.program_claim
WHERE effective_to IS NULL
GROUP BY client_id, program_code, tax_year
HAVING COUNT(*) > 1;

-- 9.2  More than one live engagement per client-program.
SELECT client_id, program_code, COUNT(*) AS live_rows
FROM tcc_ops.program_engagement
WHERE effective_to IS NULL
GROUP BY client_id, program_code
HAVING COUNT(*) > 1;

-- 9.3  More than one live resolution per finding.
SELECT client_id, finding_id, COUNT(*) AS live_rows
FROM tcc_ops.agent_finding_resolution
WHERE superseded_at IS NULL
GROUP BY client_id, finding_id
HAVING COUNT(*) > 1;

-- 9.4  More than one current row per unit-year-method.
SELECT client_id, worksite_id, program_code, method, tax_year, COUNT(*) AS current_rows
FROM tcc_gold.unit_year_master
WHERE is_current = 1
GROUP BY client_id, worksite_id, program_code, method, tax_year
HAVING COUNT(*) > 1;

-- 9.4b More than one current installment per window-year pair.
SELECT client_id, worksite_id, program_code, method, creation_year, tax_year,
       COUNT(*) AS current_rows
FROM tcc_gold.unit_credit_installment
WHERE is_current = 1
GROUP BY client_id, worksite_id, program_code, method, creation_year, tax_year
HAVING COUNT(*) > 1;

-- 9.4c Installment arithmetic that does not hold, or a window paying out more
--      jobs than it opened with, or an installment before its creation year.
--      Any hit here means a dollar on screen cannot be derived from its row.
SELECT client_id, worksite_id, creation_year, tax_year,
       tranche_jobs, jobs_maintained, per_job_usd, claimable_usd
FROM tcc_gold.unit_credit_installment
WHERE is_current = 1
  AND (   tax_year < creation_year
       OR jobs_maintained > tranche_jobs
       OR ABS(claimable_usd - ROUND(jobs_maintained * per_job_usd, 0)) > 0.51 );

-- 9.4d Annual credit that does not equal eligible jobs x the rate that was
--      applied. Same test one level up.
SELECT client_id, worksite_id, tax_year, method,
       eligible_jobs, per_job_usd, annual_credit_usd
FROM tcc_gold.unit_year_master
WHERE is_current = 1
  AND eligible_jobs IS NOT NULL
  AND per_job_usd IS NOT NULL
  AND ABS(annual_credit_usd - ROUND(eligible_jobs * per_job_usd, 0)) > 0.51;

-- 9.4e New jobs created exceeding net-new above base. Fresh creation is measured
--      against the high-water mark, which never sits below the base, so it can
--      never exceed net-new. If it does, the high-water mark was reset.
SELECT client_id, worksite_id, tax_year, method,
       net_new_vs_base, new_jobs_created, high_water_mark
FROM tcc_gold.unit_year_master
WHERE is_current = 1
  AND new_jobs_created > net_new_vs_base + 0.01;

-- 9.5  Declined claims with no reason. SQLite refuses these at write time.
SELECT claim_id, client_id, program_code, tax_year
FROM tcc_ops.program_claim
WHERE status = 'declined'
  AND (decline_reason IS NULL OR LTRIM(RTRIM(decline_reason)) = '');

-- 9.6  Values outside the domain enums. Fabric will accept anything.
SELECT DISTINCT status FROM tcc_ops.program_claim
WHERE status NOT IN ('not_assessed','assessed','proposed','declined',
                     'claimed','certified','amended');

SELECT DISTINCT provenance FROM tcc_ops.program_claim
WHERE provenance NOT IN ('computed','filed_by_us','client_asserted',
                         'inherited','authority_confirmed');

SELECT DISTINCT scope FROM tcc_ops.program_engagement
WHERE scope NOT IN ('in_scope','out_of_scope','prospective');

SELECT DISTINCT resolution FROM tcc_ops.agent_finding_resolution
WHERE resolution NOT IN ('accept','assign','drop','flag');

SELECT DISTINCT method FROM tcc_gold.employee_eligibility
WHERE method NOT IN ('min_max','pay_period');

SELECT DISTINCT status FROM tcc_gold.unit_year_master
WHERE status NOT IN ('base','above_minimum','below_minimum','partial','no_data',
                     'before_base','in_progress');

SELECT DISTINCT threshold_source FROM tcc_gold.unit_year_master
WHERE threshold_source IS NOT NULL
  AND threshold_source NOT IN ('designation','rule_pack');

SELECT DISTINCT tier_source FROM tcc_gold.unit_year_master
WHERE tier_source IS NOT NULL
  AND tier_source NOT IN ('prototype','unassigned');

-- 9.7  Orphaned run references. Every calculation row must tie to a manifest.
SELECT DISTINCT g.run_id
FROM tcc_gold.unit_month_summary g
LEFT JOIN tcc_ops.run_manifest r ON r.run_id = g.run_id
WHERE r.run_id IS NULL;

-- 9.8  Average headcount must equal total / 12. Catches a divisor "fix".
SELECT client_id, tax_year, method, worksite_id, total, average_headcount
FROM tcc_gold.unit_month_summary
WHERE ABS(average_headcount - (total / 12.0)) > 0.01;

-- 9.9  A model wrote a number. is_deterministic_path must be true for anything
--      touching a figure — agents narrate, tools calculate.
SELECT action_id, agent_name, occurred_at
FROM tcc_ops.agent_action_audit
WHERE is_deterministic_path = 0
  AND run_id IS NOT NULL;


-- 9.10 More than one live artifact at the same path.                (NEW 2.0)
SELECT container_name, blob_path, COUNT(*) AS live_rows
FROM tcc_ops.artifact
WHERE superseded_at IS NULL
GROUP BY container_name, blob_path
HAVING COUNT(*) > 1;

-- 9.11 An output blob outside its tenant's prefix, or a claim package with no
--      client or run. Either breaks the download authorization.     (NEW 2.0)
SELECT artifact_id, kind, client_id, run_id, blob_path
FROM tcc_ops.artifact
WHERE (kind = 'claim_package' AND (client_id IS NULL OR run_id IS NULL))
   OR (container_name = 'outputs'
       AND blob_path NOT LIKE CAST(client_id AS VARCHAR(20)) + '/%');

-- 9.12 Values outside the Group G enums.                            (NEW 2.0)
SELECT DISTINCT kind FROM tcc_ops.artifact
WHERE kind NOT IN ('rule_source','claim_package');

SELECT DISTINCT outcome FROM tcc_ops.artifact_access
WHERE outcome NOT IN ('served','denied','missing');

-- 9.13 Downloads of an artifact that does not exist.                (NEW 2.0)
SELECT a.access_id, a.artifact_id
FROM tcc_ops.artifact_access a
LEFT JOIN tcc_ops.artifact r ON r.artifact_id = a.artifact_id
WHERE r.artifact_id IS NULL;

/* ============================================================================
   10. SUGGESTED BUILD ORDER

   1. tcc_ops.run_manifest, source_snapshot, source_file_manifest
      Everything else references run_id. The Gold tables are meaningless
      without it, so this comes first.

   2. tcc_gold — all six
      unit_year_master, unit_month_summary and unit_credit_installment first:
      those three back the location grid, which is the screen an operator opens
      on. Then onezero_matrix and employee_eligibility for the drill, and
      employee_period_fact last — it is the largest and the deepest.

   3. tcc_ops.program_claim, program_engagement, agent_finding_resolution
      These back the portfolio view and replace the retired Cosmos containers.
      Set CLAIM_STORE=warehouse and FINDING_STORE=warehouse.

   3a. tcc_ops.artifact, artifact_access
      Before the first claim package is generated: a blob with no artifact row
      cannot be downloaded.

   4. tcc_ops Group C and D/E
      excluded_record, exception_report_item, manual_override,
      rule_change_audit, agent_action_audit.

   5. tcc_ops.client_config
      Blocked on the EntityFiscalYearRules DDL from the partner. Do not duplicate a
      fiscal-year rule that already exists on their side.

   ============================================================================
   OPEN QUESTIONS THAT TOUCH THIS SCHEMA

   From the source schema mapping (for the partner):
     Q1  PaycheckDate is nullable. What does a null mean, and what should the
         cash-basis trim do with those rows? Today they would drop silently.
     Q2  Hours and Wages are nullable with DEFAULT 0. Is NULL the same as 0, or
         "not reported"? They must not be treated alike.
     Q3  LocationId versus WorksiteLocationId — which is authoritative for the
         One/Zero unit?
     Q4  EntityFiscalYearRules DDL. Blocks client_config and BA-01.

   From the reference dataset (for the partner):
     Q23-25  The Month-12 measuring-date cliff. A final period ending 12-15
             scores month 12 as zero; 12-16 scores ~25. A one-day pay-calendar
             difference moves a location's annual average ~8%, and therefore the
             credit. unreachable_months and the year_complete columns exist
             because of this and the rule is NOT settled.

   Three lookups still outstanding from the partner: EntityFiscalYearRules
   (highest priority), PayFrequency, PayCodeCategory.

   ============================================================================
   PROVENANCE

   Generated from:
       docs/data/OPERATIONAL-DATA-MODEL.md  v0.3   (Groups A, C, D, E, F, config)
       docs/data/GOLD-LAYER-SPEC.md         v0.1   (Group B)
       backend/infrastructure/persistence/sqlite_claims.py     (Group F columns)
       backend/infrastructure/persistence/sqlite_findings.py   (Group F columns)
       backend/domain/claims.py                                (enum values)
   at commit 9c572a9 on 2026-09-14 (v1.2), revised to v2.0 on 2026-10-08 from
       backend/infrastructure/persistence/cosmos_claims.py     (retired)
       backend/infrastructure/persistence/cosmos_findings.py   (retired)
       infra/main.bicep  Cosmos container list                 (retired)

   Group F column definitions were verified column-for-column against the
   application code; the enum values in the constraint-intent blocks come from
   domain/claims.py rather than from prose.

   Companion documents, same folder:
       Source Schema Mapping        Bronze/Silver — the partner's source to the engine
       Gold Layer Spec              Group B in narrative form, with volumetrics
       Operational Data Model v0.3  Groups A and C-F in narrative form
   ============================================================================ */


/* ----------------------------------------------------------------------------
   INDEXES

   Generated from the section 1a access patterns. Fabric Warehouse rejects
   CREATE INDEX, so on that platform these exist only as documentation; here
   they are real. Both come from the same table, so they cannot disagree.
   ---------------------------------------------------------------------------- */

CREATE INDEX ix_run_manifest
    ON tcc_ops.run_manifest (client_id, program_code, tax_year);
GO

CREATE INDEX ix_source_snapshot
    ON tcc_ops.source_snapshot (client_id, extracted_at);
GO

CREATE INDEX ix_employee_period_fact
    ON tcc_gold.employee_period_fact (client_id, tax_year, employee_id);
GO

CREATE INDEX ix_employee_period_fact_2
    ON tcc_gold.employee_period_fact (record_token, pay_period_start);
GO

CREATE INDEX ix_employee_eligibility
    ON tcc_gold.employee_eligibility (client_id, tax_year, method, employee_id);
GO

CREATE INDEX ix_onezero_matrix
    ON tcc_gold.onezero_matrix (client_id, tax_year, method, worksite_id);
GO

CREATE INDEX ix_unit_month_summary
    ON tcc_gold.unit_month_summary (client_id, tax_year, method, worksite_id);
GO

CREATE INDEX ix_unit_year_master
    ON tcc_gold.unit_year_master (client_id, worksite_id, tax_year);
GO

CREATE INDEX ix_unit_credit_installment
    ON tcc_gold.unit_credit_installment (client_id, worksite_id, tax_year);
GO

CREATE INDEX ix_excluded_record
    ON tcc_ops.excluded_record (client_id, run_id, employee_id);
GO

CREATE INDEX ix_manual_override
    ON tcc_ops.manual_override (client_id, run_id, scope);
GO

CREATE INDEX ix_exception_report_item
    ON tcc_ops.exception_report_item (client_id, run_id, disposition);
GO

CREATE INDEX ix_rule_pack_version
    ON tcc_ops.rule_pack_version (program_code, tax_year);
GO

CREATE INDEX ix_agent_action_audit
    ON tcc_ops.agent_action_audit (client_id, occurred_at);
GO

CREATE INDEX ix_program_claim
    ON tcc_ops.program_claim (client_id, program_code, tax_year);
GO

CREATE INDEX ix_program_claim_2
    ON tcc_ops.program_claim (client_id, tax_year);
GO

CREATE INDEX ix_program_engagement
    ON tcc_ops.program_engagement (client_id, program_code, effective_from);
GO

CREATE INDEX ix_agent_finding_resolution
    ON tcc_ops.agent_finding_resolution (client_id, tax_year, finding_id);
GO

CREATE INDEX ix_artifact
    ON tcc_ops.artifact (client_id, kind, tax_year, created_at);
GO

CREATE INDEX ix_artifact_2
    ON tcc_ops.artifact (container_name, blob_path);
GO

CREATE INDEX ix_artifact_access
    ON tcc_ops.artifact_access (client_id, accessed_at);
GO

CREATE INDEX ix_client_config
    ON tcc_ops.client_config (client_id, effective_from);
GO
