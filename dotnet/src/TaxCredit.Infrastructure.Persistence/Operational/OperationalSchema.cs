using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Explicit supplemental operational schema after PersistenceSchema.Initialize; seed reset must clear the finding audit too.</summary>
public static class OperationalSchema
{
    /// <summary>Closed qualified inventory of all tables these operational adapters read or write; usable by hermetic reset.</summary>
    public static IReadOnlyList<string> TableNames { get; } = Array.AsReadOnly<string>(
    [
        "ops.program_claim", "ops.program_engagement", "ops.manual_override", "ops.run_manifest",
        "ops.run_batch_item", "ops.run_batch", "ops.program_draft_document", "ops.program_draft_event",
        "ops.program_draft", "ops.lookup_override", "ops.lookup_audit", "ops.agent_finding_resolution",
        "ops.finding_audit", "ops.artifact_access", "ops.artifact", "ops.channel_confirmation",
        "ops.channel_user", "ops.channel_audit", "ops.agent_action_audit",
        "ops.write_sequence", "ops.run_work_identity", "ops.run_source_observation",
    ]);

    /// <summary>Local supplemental tables; deployed provisioning must explicitly supply the equivalent native DDL.</summary>
    public static IReadOnlyList<string> SupplementalTableNames { get; } = Array.AsReadOnly<string>(
        ["ops.finding_audit", "ops.write_sequence", "ops.run_work_identity", "ops.run_source_observation"]);

    /// <summary>Adds the attributed reopen audit missing from the checked-in base schema, without changing existing tables.</summary>
    public static void Initialize(PersistenceDatabase database)
    {
        ArgumentNullException.ThrowIfNull(database);
        database.Transact(session =>
        {
            var declaration = "(audit_id VARCHAR(64) NOT NULL, client_id BIGINT NOT NULL, finding_id VARCHAR(128) NOT NULL, "
                + "action VARCHAR(16) NOT NULL, actor VARCHAR(256) NOT NULL, at VARCHAR(40) NOT NULL)";
            var sql = session.Dialect is SqliteDialect
                ? "CREATE TABLE IF NOT EXISTS {ops.finding_audit} " + declaration
                : "IF OBJECT_ID('{ops.finding_audit}', 'U') IS NULL CREATE TABLE {ops.finding_audit} " + declaration;
            session.ExecuteExempt(SqlExemption.Schema, sql);
            if (session.Dialect is SqliteDialect)
            {
                OverrideOrder.UpgradeLocal(session);
                session.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE IF NOT EXISTS {ops.run_work_identity} "
                    + "(client_id INTEGER NOT NULL,item_id TEXT NOT NULL,run_id TEXT NOT NULL,PRIMARY KEY(client_id,item_id)) STRICT");
                session.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE IF NOT EXISTS {ops.run_source_observation} "
                    + "(client_id INTEGER NOT NULL,run_id TEXT NOT NULL,observation_json TEXT NOT NULL,PRIMARY KEY(client_id,run_id)) STRICT");
            }

            return true;
        });
    }
}
