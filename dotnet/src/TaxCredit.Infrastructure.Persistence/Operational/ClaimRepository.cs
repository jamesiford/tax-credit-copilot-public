using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Append-only claims and engagements in the same database as Gold; money retains its recorded decimal lexeme.</summary>
public sealed class ClaimRepository(PersistenceDatabase database) : IClaimRepository, IClaimSink
{
    /// <summary>Indicates that accepted records survive reopening the configured database.</summary>
    public bool IsDurable { get; } = true;

    /// <inheritdoc />
    public ProgramClaim? Current(long clientId, string programCode, long taxYear)
    {
        using var session = database.Open();
        return session.Query(clientId, ClaimRows.Select + " WHERE {tenant} AND program_code = ? AND tax_year = ? AND effective_to IS NULL",
            PyStr.Upper(programCode), taxYear).Select(ClaimRows.Claim).SingleOrDefault();
    }

    /// <inheritdoc />
    public IReadOnlyList<ProgramClaim> History(long clientId, string programCode, long taxYear)
    {
        using var session = database.Open();
        return session.Query(clientId, ClaimRows.Select + " WHERE {tenant} AND program_code = ? AND tax_year = ? "
            + "ORDER BY effective_from, CASE WHEN effective_to IS NULL THEN 1 ELSE 0 END, decided_at, claim_id",
            PyStr.Upper(programCode), taxYear).Select(ClaimRows.Claim).ToArray();
    }

    /// <inheritdoc />
    public IReadOnlyList<ProgramClaim> Coverage(long clientId, IEnumerable<string>? programCodes = null, IEnumerable<long>? taxYears = null)
    {
        var sql = ClaimRows.Select + " WHERE {tenant} AND effective_to IS NULL";
        var args = new List<object?>();
        if (!Filter(ref sql, args, "program_code", programCodes?.Select(PyStr.Upper)) || !Filter(ref sql, args, "tax_year", taxYears))
        {
            return [];
        }

        using var session = database.Open();
        return session.Query(clientId, sql + " ORDER BY program_code, tax_year", args.ToArray()).Select(ClaimRows.Claim).ToArray();
    }

    /// <inheritdoc />
    public IReadOnlyList<ProgramClaim> PortfolioCoverage(IEnumerable<long>? clientIds = null, IEnumerable<long>? taxYears = null)
    {
        var sql = ClaimRows.Select + " WHERE effective_to IS NULL";
        var args = new List<object?>();
        if (!Filter(ref sql, args, "client_id", clientIds) || !Filter(ref sql, args, "tax_year", taxYears))
        {
            return [];
        }

        using var session = database.Open();
        return session.QueryExempt(SqlExemption.Portfolio, sql + " ORDER BY client_id, program_code, tax_year", args.ToArray())
            .Select(ClaimRows.Claim).ToArray();
    }

    /// <inheritdoc />
    public ProgramClaim Record(ProgramClaim claim)
    {
        ArgumentNullException.ThrowIfNull(claim);
        return database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.Validation, "SELECT claim_id FROM tcc_ops.program_claim WHERE claim_id = ?", claim.ClaimId).Count != 0)
            {
                throw new InvalidOperationException("The claim identity is already recorded; reload it or use a new identity for a transition.");
            }

            session.Execute(claim.ClientId, "UPDATE tcc_ops.program_claim SET effective_to = ? "
                + "WHERE {tenant} AND program_code = ? AND tax_year = ? AND effective_to IS NULL",
                OpsRow.EffectiveDate(session, claim.EffectiveFrom), claim.ProgramCode, claim.TaxYear);
            session.Insert(claim.ClientId, "tcc_ops.program_claim", ClaimRows.Columns, [ClaimRows.Values(session, claim)]);
            return claim;
        });
    }

    void IClaimSink.Record(ProgramClaim claim) => Record(claim);

    /// <inheritdoc />
    public IReadOnlyList<ProgramEngagement> Engagements(long clientId)
    {
        using var session = database.Open();
        return session.Query(clientId, "SELECT " + string.Join(", ", ClaimRows.EngagementColumns)
            + " FROM tcc_ops.program_engagement WHERE {tenant} AND effective_to IS NULL ORDER BY program_code")
            .Select(ClaimRows.Engagement).ToArray();
    }

    /// <inheritdoc />
    public ProgramEngagement SetEngagement(ProgramEngagement engagement)
    {
        ArgumentNullException.ThrowIfNull(engagement);
        return database.Transact(session =>
        {
            session.Execute(engagement.ClientId, "UPDATE tcc_ops.program_engagement SET effective_to = ? "
                + "WHERE {tenant} AND program_code = ? AND effective_to IS NULL", OpsRow.EffectiveDate(session, engagement.EffectiveFrom), engagement.ProgramCode);
            session.Insert(engagement.ClientId, "tcc_ops.program_engagement", ClaimRows.EngagementColumns,
                [new object?[] { engagement.ClientId, engagement.ProgramCode, engagement.Scope.Value(), OpsRow.EffectiveDate(session, engagement.EffectiveFrom),
                    OpsRow.EffectiveDate(session, engagement.EffectiveTo), engagement.Note, engagement.SetBy, OpsRow.Timestamp(session, engagement.SetAt) }]);
            return engagement;
        });
    }

    private static bool Filter<T>(ref string sql, List<object?> args, string column, IEnumerable<T>? selector)
    {
        if (selector is null)
        {
            return true;
        }

        var values = selector.Distinct().ToArray();
        if (values.Length == 0)
        {
            return false;
        }

        sql += $" AND {column} IN ({string.Join(", ", values.Select(_ => "?"))})";
        args.AddRange(values.Select(value => (object?)value));
        return true;
    }
}
