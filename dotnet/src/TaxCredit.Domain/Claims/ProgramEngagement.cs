using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>Whether we are engaged to handle a program for a client at all (Python <c>ProgramEngagement</c>, a frozen dataclass).</summary>
public sealed record ProgramEngagement
{
    private readonly string _programCode = string.Empty;

    /// <summary>The tenant.</summary>
    public long ClientId { get; init; }

    /// <summary>The programme code; upper-cased on construction like Python's <c>__post_init__</c>.</summary>
    public string ProgramCode
    {
        get => _programCode;
        init => _programCode = PyStr.Upper(value);
    }

    /// <summary>The scope (default <c>prospective</c>).</summary>
    public EngagementScope Scope { get; init; } = EngagementScope.Prospective;

    /// <summary>When the entry took effect (default: now, UTC).</summary>
    public PyDateTime EffectiveFrom { get; init; } = PyDateTime.UtcNow();

    /// <summary>When the entry was superseded.</summary>
    public PyDateTime? EffectiveTo { get; init; }

    /// <summary>A free-text note.</summary>
    public string? Note { get; init; }

    /// <summary>Who set it; <c>null</c> on rows recorded before CH-04 (an old engagement stays unattributed rather than being given a name).</summary>
    public string? SetBy { get; init; }

    /// <summary>When it was set.</summary>
    public PyDateTime? SetAt { get; init; }

    /// <summary>Python <c>to_dict()</c>.</summary>
    /// <returns>An ordered tree in Python's key order.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("client_id", ClientId)
        .Add("program_code", ProgramCode)
        .Add("scope", Scope.Value())
        .Add("effective_from", EffectiveFrom.IsoFormat())
        .Add("effective_to", EffectiveTo?.IsoFormat())
        .Add("note", Note)
        .Add("set_by", SetBy)
        .Add("set_at", SetAt?.IsoFormat());
}

/// <summary>
/// The claim storage port (Python <c>ClaimRepository</c> Protocol), named for capability, not for a database. Every read takes
/// <c>clientId</c> because tenant is the partition key, not a predicate: a query that could omit it could leak one client's figures
/// onto another's screen. Declared only; the implementations belong to the infrastructure layer.
/// </summary>
public interface IClaimRepository
{
    /// <summary>The live record for one cell, or <c>null</c> if never recorded.</summary>
    /// <param name="clientId">The tenant.</param>
    /// <param name="programCode">The programme code.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <returns>The live claim or <c>null</c>.</returns>
    ProgramClaim? Current(long clientId, string programCode, long taxYear);

    /// <summary>Every record for one cell, oldest first.</summary>
    /// <param name="clientId">The tenant.</param>
    /// <param name="programCode">The programme code.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <returns>The history.</returns>
    IReadOnlyList<ProgramClaim> History(long clientId, string programCode, long taxYear);

    /// <summary>Live records for one client, optionally narrowed.</summary>
    /// <param name="clientId">The tenant.</param>
    /// <param name="programCodes">Restrict to these programmes, or <c>null</c> for all.</param>
    /// <param name="taxYears">Restrict to these years, or <c>null</c> for all.</param>
    /// <returns>The live records.</returns>
    IReadOnlyList<ProgramClaim> Coverage(long clientId, IEnumerable<string>? programCodes = null, IEnumerable<long>? taxYears = null);

    /// <summary>Live records across clients: the portfolio matrix.</summary>
    /// <param name="clientIds">Restrict to these clients, or <c>null</c> for all.</param>
    /// <param name="taxYears">Restrict to these years, or <c>null</c> for all.</param>
    /// <returns>The live records.</returns>
    IReadOnlyList<ProgramClaim> PortfolioCoverage(IEnumerable<long>? clientIds = null, IEnumerable<long>? taxYears = null);

    /// <summary>Appends a record, closing whatever it supersedes.</summary>
    /// <param name="claim">The record to append.</param>
    /// <returns>What was stored.</returns>
    ProgramClaim Record(ProgramClaim claim);

    /// <summary>Live engagement scope for one client.</summary>
    /// <param name="clientId">The tenant.</param>
    /// <returns>The live engagements.</returns>
    IReadOnlyList<ProgramEngagement> Engagements(long clientId);

    /// <summary>Appends engagement scope, closing the prior entry for that program.</summary>
    /// <param name="engagement">The engagement to append.</param>
    /// <returns>What was stored.</returns>
    ProgramEngagement SetEngagement(ProgramEngagement engagement);
}
