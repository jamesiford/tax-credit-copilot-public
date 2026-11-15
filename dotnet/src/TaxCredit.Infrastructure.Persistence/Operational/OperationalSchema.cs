using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Explicit supplemental operational schema after PersistenceSchema.Initialize; seed reset must clear the finding audit too.</summary>
public static class OperationalSchema
{
    /// <summary>Closed qualified inventory of all tables these operational adapters read or write; usable by hermetic reset.</summary>
    public static IReadOnlyList<string> TableNames { get; } = Array.AsReadOnly<string>(
    [
        "tcc_ops.program_claim", "tcc_ops.program_engagement", "tcc_ops.manual_override", "tcc_ops.run_manifest",
        "tcc_ops.run_batch_item", "tcc_ops.run_batch", "tcc_ops.program_draft_document", "tcc_ops.program_draft_event",
        "tcc_ops.program_draft", "tcc_ops.lookup_override", "tcc_ops.lookup_audit", "tcc_ops.agent_finding_resolution",
        "tcc_ops.finding_audit", "tcc_ops.artifact_access", "tcc_ops.artifact", "tcc_ops.channel_confirmation",
        "tcc_ops.channel_user", "tcc_ops.channel_audit", "tcc_ops.agent_action_audit",
    ]);

    /// <summary>The only table these adapters add beyond the checked-in central DDL; its SQLite name is tcc_ops_finding_audit.</summary>
    public static IReadOnlyList<string> SupplementalTableNames { get; } = Array.AsReadOnly<string>(["tcc_ops.finding_audit"]);

    /// <summary>Adds the attributed reopen audit missing from the checked-in base schema, without changing existing tables.</summary>
    public static void Initialize(PersistenceDatabase database)
    {
        ArgumentNullException.ThrowIfNull(database);
        database.Transact(session =>
        {
            var declaration = "(audit_id VARCHAR(64) NOT NULL, client_id BIGINT NOT NULL, finding_id VARCHAR(128) NOT NULL, "
                + "action VARCHAR(16) NOT NULL, actor VARCHAR(256) NOT NULL, at VARCHAR(40) NOT NULL)";
            var sql = session.Dialect is SqliteDialect
                ? "CREATE TABLE IF NOT EXISTS tcc_ops.finding_audit " + declaration
                : "IF OBJECT_ID('tcc_ops.finding_audit', 'U') IS NULL CREATE TABLE tcc_ops.finding_audit " + declaration;
            session.ExecuteExempt(SqlExemption.Schema, sql);
            return true;
        });
    }
}
