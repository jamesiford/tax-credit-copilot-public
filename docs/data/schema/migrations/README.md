# Schema migrations

Forward-only changes to the Warehouse schema after the DDL v2.0 bootstrap (D22).

- **The bootstrap is `../tcc-schema.fabric.sql`.** It is destructive and runs at
  most once per Warehouse, recording version `0000` in
  `tcc_ops.schema_migration`. It runs only on a Warehouse Terraform has just
  created or one explicitly approved for a rebuild.
- **Every later change is a file here, named `NNNN_<slug>.sql`**, starting at
  `0001`. Batches are separated by `GO` lines, exactly as in the bootstrap.
- **A migration is immutable once applied.** The runner records its SHA-256 and
  refuses to continue if a recorded file changes. Fix a mistake with the next
  migration.
- Apply with `python scripts/apply-migrations.py --target <target>`. It applies
  every unrecorded version in order and records each; a re-run applies nothing.
  `azd up` runs it after every provision.
- Write T-SQL that runs on both Fabric Warehouse and SQL Server (no `CREATE
  INDEX`, no `IDENTITY`, no `MERGE`), and regenerate the SQL Server variant of
  the bootstrap only if the bootstrap itself changes.

The set is `0001_channel_audit.sql` (the Microsoft 365 channel's audit trail, writer
allow-list and write confirmations) and `0002_engagement_actor.sql` (who set a
programme engagement). Keys are declared `NOT ENFORCED`, as in the bootstrap;
`generate_variants.py` strips that for SQL Server, and the same one-line strip
makes a migration run there.
