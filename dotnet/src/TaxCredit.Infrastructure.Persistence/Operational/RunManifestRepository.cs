using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>The durable manifest port used by operational routes and the Gold writer's database.</summary>
public sealed class RunManifestRepository(PersistenceDatabase database) : IRunManifestRepository
{
    private static string Select => "SELECT " + string.Join(", ", WarehouseVocabulary.RunManifestColumns) + " FROM tcc_ops.run_manifest";

    /// <summary>Indicates durable storage rather than a process-local manifest dictionary.</summary>
    public bool IsDurable { get; } = true;

    /// <inheritdoc />
    public RunManifest Record(RunManifest manifest)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        return database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ManifestIdentity, "SELECT run_id FROM tcc_ops.run_manifest WHERE run_id = ?", manifest.RunId).Count != 0)
            {
                throw new InvalidOperationException("The run identity is already recorded.");
            }

            session.Insert(manifest.ClientId, "tcc_ops.run_manifest", WarehouseVocabulary.RunManifestColumns, [Values(session, manifest)]);
            return manifest;
        });
    }

    /// <inheritdoc />
    public RunManifest? Get(string runId)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ManifestIdentity, Select + " WHERE run_id = ?", runId).Select(Hydrate).SingleOrDefault();
    }

    /// <inheritdoc />
    public RunManifest? Latest(long clientId, string? programCode = null)
    {
        using var session = database.Open();
        var sql = Select + " WHERE {tenant} AND run_status = 'success' AND superseded_by_run_id IS NULL";
        var args = new List<object?>();
        if (programCode is not null)
        {
            sql += " AND program_code = ?";
            args.Add(programCode);
        }

        return session.Query(clientId, session.Dialect.Page(sql + " ORDER BY run_started_at DESC, run_id DESC", 1, 0),
            args.ToArray()).Select(Hydrate).SingleOrDefault();
    }

    /// <inheritdoc />
    public long Count()
    {
        using var session = database.Open();
        return new OpsRow(session.QueryExempt(SqlExemption.ManifestIdentity, "SELECT COUNT(*) AS n FROM tcc_ops.run_manifest")[0]).Long("n");
    }

    private static object?[] Values(SqlSession session, RunManifest m) =>
    [
        m.RunId, m.ClientId, m.EntityId, m.ProgramCode, m.TaxYear, m.FiscalYearBegin, m.FiscalYearEnd,
        m.SourceSnapshotId, m.Step1AssumptionSetId, m.Step1AssumptionSha256, m.OnezeroAssumptionSetId, m.OnezeroAssumptionSha256,
        m.RulePackVersion, m.CodeCommit, m.CalculationId, OpsRow.Timestamp(session, m.RunStartedAt), OpsRow.Timestamp(session, m.RunCompletedAt),
        m.RunStatus, m.SupersededByRunId, m.TriggeredBy,
    ];

    private static RunManifest Hydrate(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new RunManifest(r.Required("run_id"), r.Long("client_id"), r.Required("program_code"), r.Long("tax_year"),
            r.Day("fiscal_year_begin")!.Value, r.Day("fiscal_year_end")!.Value, r.Instant("run_started_at")!.Value, r.Required("run_status"),
            r.OptionalLong("entity_id"), r.Text("source_snapshot_id"), r.Text("step1_assumption_set_id"), r.Text("step1_assumption_sha256"),
            r.Text("onezero_assumption_set_id"), r.Text("onezero_assumption_sha256"), r.Text("rule_pack_version"), r.Text("code_commit"),
            r.Text("calculation_id"), r.Instant("run_completed_at"), r.Text("superseded_by_run_id"), r.Text("triggered_by"));
    }
}
