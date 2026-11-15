using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Runs;

/// <summary>
/// One request to run a set of clients (Python <c>RunBatch</c>, a frozen dataclass). Counts are derived from the items by <c>batch_status</c>.
/// </summary>
/// <remarks>
/// Equality follows the generated <c>__eq__</c>: field by field, the three dict fields as dicts (order-insensitive, <c>1 == 1.0</c>) and
/// <see cref="TaxYears"/> as a tuple. Python's <c>hash()</c> always raises <c>TypeError: unhashable type: 'dict'</c> (the dicts are fields),
/// so <see cref="HashableInPython"/> is <c>false</c> and <see cref="GetHashCode"/> hashes the scalar fields instead of throwing.
/// </remarks>
public sealed record RunBatch
{
    /// <summary>The batch id.</summary>
    public required string BatchId { get; init; }

    /// <summary>What it does for each client.</summary>
    public required BatchKind Kind { get; init; }

    /// <summary>How the clients were chosen.</summary>
    public required ScopeKind ScopeKind { get; init; }

    /// <summary>The selection, as given.</summary>
    public required PyDict ScopeSpec { get; init; }

    /// <summary>Who asked.</summary>
    public required string RequestedBy { get; init; }

    /// <summary>When it was asked.</summary>
    public required PyDateTime RequestedAt { get; init; }

    /// <summary>A programme to restrict to.</summary>
    public string? ProgramCode { get; init; }

    /// <summary>The tax years asked for (Python tuple); empty means the client's latest runnable year.</summary>
    public IReadOnlyList<long> TaxYears { get; init; } = [];

    /// <summary>Run even when nothing changed.</summary>
    public bool Force { get; init; }

    /// <summary>Whether a changed code commit counts as a change.</summary>
    public bool IncludeCodeCommit { get; init; }

    /// <summary>One item per client, not per year.</summary>
    public bool RefreshOnce { get; init; } = true;

    /// <summary>Opt-in. Skipping happens only when this is true and <see cref="Force"/> is false. [F04b.1]</summary>
    public bool SkipUnchanged { get; init; }

    /// <summary>Where the batch is.</summary>
    public BatchStatus Status { get; init; } = BatchStatus.Queued;

    /// <summary>The idempotency key of the request.</summary>
    public string? IdempotencyKey { get; init; }

    /// <summary>The preview's summary; a fresh dict per instance, as Python's <c>default_factory</c>.</summary>
    public PyDict DryRunSummary { get; init; } = new();

    /// <summary>Whether cancel was requested.</summary>
    public bool CancelRequested { get; init; }

    /// <summary>When the first item started.</summary>
    public PyDateTime? StartedAt { get; init; }

    /// <summary>When the last item finished.</summary>
    public PyDateTime? FinishedAt { get; init; }

    /// <summary>Items per status value; a fresh dict per instance.</summary>
    public PyDict Counts { get; init; } = new();

    /// <summary>Whether Python's <c>hash()</c> would succeed: it never does (a dict is a field).</summary>
    public static bool HashableInPython => false;

    /// <inheritdoc />
    public bool Equals(RunBatch? other) =>
        other is not null
        && BatchId == other.BatchId && Kind == other.Kind && ScopeKind == other.ScopeKind && PyEquality.Equal(ScopeSpec, other.ScopeSpec)
        && RequestedBy == other.RequestedBy && RequestedAt.Equals(other.RequestedAt) && ProgramCode == other.ProgramCode
        && TaxYears.SequenceEqual(other.TaxYears) && Force == other.Force && IncludeCodeCommit == other.IncludeCodeCommit
        && RefreshOnce == other.RefreshOnce && SkipUnchanged == other.SkipUnchanged && Status == other.Status && IdempotencyKey == other.IdempotencyKey
        && PyEquality.Equal(DryRunSummary, other.DryRunSummary) && CancelRequested == other.CancelRequested
        && Nullable.Equals(StartedAt, other.StartedAt) && Nullable.Equals(FinishedAt, other.FinishedAt) && PyEquality.Equal(Counts, other.Counts);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(BatchId, Kind, ScopeKind, RequestedBy, RequestedAt, ProgramCode, Status);
}
