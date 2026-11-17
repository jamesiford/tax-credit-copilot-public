using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Findings;

/// <summary>A human's answer to something an agent found (Python <c>FindingResolution</c>, a frozen dataclass). [ADR-003]</summary>
/// <remarks>
/// Equality follows Python's generated <c>__eq__</c>: a field-by-field comparison where <see cref="Detail"/> compares as a dict
/// (order-insensitive, <c>1 == 1.0</c>). Python's <c>hash()</c> raises <c>TypeError: unhashable type: 'dict'</c> when
/// <see cref="Detail"/> is set; <see cref="GetHashCode"/> here ignores the detail instead of throwing, because a C# hash that throws would
/// break every hash-based collection, so <see cref="HashableInPython"/> carries the fact.
/// </remarks>
public sealed record FindingResolution
{
    /// <summary>The finding answered.</summary>
    public required string FindingId { get; init; }

    /// <summary>The tenant.</summary>
    public required long ClientId { get; init; }

    /// <summary>The tax year.</summary>
    public required long TaxYear { get; init; }

    /// <summary>The answer: <c>accept</c>, <c>assign</c>, <c>drop</c> or <c>flag</c> (not validated, as in Python).</summary>
    public required string Resolution { get; init; }

    /// <summary>Who decided.</summary>
    public required string DecidedBy { get; init; }

    /// <summary>When it was decided (the text as stored).</summary>
    public required string DecidedAt { get; init; }

    /// <summary>Extra detail, for example which worksite to keep.</summary>
    public PyDict? Detail { get; init; }

    /// <summary>A free-text note.</summary>
    public string? Note { get; init; }

    /// <summary>When a later decision superseded this one.</summary>
    public string? SupersededAt { get; init; }

    /// <summary>Whether Python's <c>hash()</c> would succeed: it raises for a non-<c>None</c> dict detail.</summary>
    public bool HashableInPython => Detail is null;

    /// <summary>Python <c>to_dict()</c>: the nine fields in Python's order. <see cref="Detail"/> is returned as the same object, not a copy.</summary>
    /// <returns>An ordered tree.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("finding_id", FindingId)
        .Add("client_id", ClientId)
        .Add("tax_year", TaxYear)
        .Add("resolution", Resolution)
        .Add("detail", Detail)
        .Add("note", Note)
        .Add("decided_by", DecidedBy)
        .Add("decided_at", DecidedAt)
        .Add("superseded_at", SupersededAt);

    /// <inheritdoc />
    public bool Equals(FindingResolution? other) =>
        other is not null
        && FindingId == other.FindingId && ClientId == other.ClientId && TaxYear == other.TaxYear && Resolution == other.Resolution
        && DecidedBy == other.DecidedBy && DecidedAt == other.DecidedAt && Note == other.Note && SupersededAt == other.SupersededAt
        && PyEquality.Equal(Detail, other.Detail);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(FindingId, ClientId, TaxYear, Resolution, DecidedBy, DecidedAt, Note, SupersededAt);
}
