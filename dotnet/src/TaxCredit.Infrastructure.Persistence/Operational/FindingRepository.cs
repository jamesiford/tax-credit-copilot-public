using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Append-only scoped finding decisions; reopening is independently attributed in the audit.</summary>
public sealed class FindingRepository(PersistenceDatabase database, IIdSource? ids = null) : IFindingRepository
{
    private static readonly string[] Columns =
    [
        "finding_id", "client_id", "tax_year", "resolution", "detail", "note", "decided_by", "decided_at", "superseded_at",
    ];
    private static string Select => "SELECT " + string.Join(", ", Columns) + " FROM tcc_ops.agent_finding_resolution";

    /// <inheritdoc />
    public IReadOnlyList<FindingResolution> Live(long clientId, long? taxYear = null)
    {
        using var session = database.Open();
        return session.Query(clientId, Select + " WHERE {tenant} AND superseded_at IS NULL"
            + (taxYear is null ? "" : " AND tax_year = ?") + " ORDER BY finding_id", taxYear is null ? [] : [taxYear]).Select(Hydrate).ToArray();
    }

    /// <inheritdoc />
    public IReadOnlyList<FindingResolution> History(long clientId, string findingId)
    {
        using var session = database.Open();
        return session.Query(clientId, Select + " WHERE {tenant} AND finding_id = ? "
            + "ORDER BY decided_at, CASE WHEN superseded_at IS NULL THEN 1 ELSE 0 END", findingId).Select(Hydrate).ToArray();
    }

    /// <inheritdoc />
    public FindingResolution Record(FindingResolution resolution)
    {
        ArgumentNullException.ThrowIfNull(resolution);
        if (resolution.Resolution is not ("accept" or "assign" or "drop" or "flag") || resolution.SupersededAt is not null)
        {
            throw new ArgumentException("A new resolution must have a valid live decision.", nameof(resolution));
        }

        return database.Transact(session =>
        {
            session.Execute(resolution.ClientId, "UPDATE tcc_ops.agent_finding_resolution SET superseded_at = ? "
                + "WHERE {tenant} AND finding_id = ? AND superseded_at IS NULL", OpsRow.Timestamp(session, resolution.DecidedAt), resolution.FindingId);
            session.Insert(resolution.ClientId, "tcc_ops.agent_finding_resolution", Columns,
                [new object?[] { resolution.FindingId, resolution.ClientId, resolution.TaxYear, resolution.Resolution, OpsRow.Json(resolution.Detail),
                    resolution.Note, resolution.DecidedBy, OpsRow.Timestamp(session, resolution.DecidedAt), null }]);
            AppendAudit(session, resolution.ClientId, resolution.FindingId, "resolve", resolution.DecidedBy, resolution.DecidedAt);
            return resolution;
        });
    }

    /// <inheritdoc />
    public bool Reopen(long clientId, string findingId, string decidedBy, PyDateTime at) => database.Transact(session =>
    {
        var changed = session.Execute(clientId, "UPDATE tcc_ops.agent_finding_resolution SET superseded_at = ? "
            + "WHERE {tenant} AND finding_id = ? AND superseded_at IS NULL", OpsRow.Clock(session, at), findingId);
        if (changed != 0)
        {
            AppendAudit(session, clientId, findingId, "reopen", decidedBy, OpsRow.Clock(at));
        }

        return changed != 0;
    });

    /// <inheritdoc />
    public IReadOnlyList<FindingAudit> Audit(long clientId, string findingId)
    {
        using var session = database.Open();
        return session.Query(clientId, "SELECT finding_id, client_id, action, actor, at FROM tcc_ops.finding_audit "
            + "WHERE {tenant} AND finding_id = ? ORDER BY at, audit_id", findingId).Select(values =>
            {
                var r = new OpsRow(values);
                return new FindingAudit(r.Required("finding_id"), r.Long("client_id"), r.Required("action"), r.Required("actor"), r.Instant("at")!.Value);
            }).ToArray();
    }

    private static FindingResolution Hydrate(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new FindingResolution
        {
            FindingId = r.Required("finding_id"),
            ClientId = r.Long("client_id"),
            TaxYear = r.Long("tax_year"),
            Resolution = r.Required("resolution"),
            Detail = r.Document("detail"),
            Note = r.Text("note"),
            DecidedBy = r.Required("decided_by"),
            DecidedAt = r.Required("decided_at"),
            SupersededAt = r.Instant("superseded_at")?.IsoFormat(),
        };
    }

    private void AppendAudit(SqlSession session, long clientId, string findingId, string action, string actor, string at) =>
        session.Insert(clientId, "tcc_ops.finding_audit", ["audit_id", "client_id", "finding_id", "action", "actor", "at"],
            [new object?[] { (ids?.NewId() ?? Guid.NewGuid()).ToString(), clientId, findingId, action, actor, at }]);
}
