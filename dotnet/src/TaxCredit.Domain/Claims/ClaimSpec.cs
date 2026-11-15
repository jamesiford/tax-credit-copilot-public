using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>Mirrors Python <c>ClaimError</c> (a <c>ValueError</c> subclass): a claim was rejected for a domain reason, not a storage one.</summary>
/// <param name="message">What was rejected and why.</param>
public sealed class ClaimError(string message) : PyException("ClaimError", message);

/// <summary>The money coercion <c>domain/claims.py</c> applies at the boundary (<c>_money</c>) and its constants.</summary>
public static class ClaimMoney
{
    /// <summary>Dollar equality tolerance: two figures within this are "the same claim" (Python <c>MATERIALITY_USD</c>, <c>Decimal("1.00")</c>).</summary>
    public static PyDecimal Materiality { get; } = new(false, new BigInteger(100), -2);

    /// <summary>Python <c>_money(value)</c>: <c>None</c> is zero, a <c>Decimal</c> is kept as is, anything else goes through <c>Decimal(str(value))</c>.</summary>
    /// <remarks>
    /// Why through <c>str</c>: a float 0.1 becomes exactly <c>Decimal("0.1")</c> rather than its 55-digit binary expansion. A bool or a list
    /// stringifies to text that is never a number, so it raises <c>ConversionSyntax</c> like any other junk. NaN and infinities are not modelled.
    /// </remarks>
    /// <param name="value">A <see cref="PyDecimal"/>, int, float, text or <c>null</c>.</param>
    /// <returns>The exact decimal.</returns>
    /// <exception cref="PyInvalidOperation">For a value Python's <c>Decimal(str(value))</c> rejects.</exception>
    public static PyDecimal Of(object? value) => value switch
    {
        null => PyDecimalOps.Zero,
        PyDecimal d => d,
        long l => PyDecimalOps.FromInt(l),
        int i => PyDecimalOps.FromInt(i),
        BigInteger b => PyDecimalOps.FromInt(b),
        double f when !double.IsFinite(f) => throw new PyUnsupportedException("Decimal of a NaN or infinite float is not modelled by this port"),
        double f => PyDecimal.FromFloatViaStr(f),
        string s => PyDecimalOps.FromString(s),
        _ => throw new PyInvalidOperation("[<class 'decimal.ConversionSyntax'>]"),
    };
}

/// <summary>The inputs of <see cref="ProgramClaim.Create"/>, one property per Python dataclass field with the same defaults.</summary>
public sealed record ClaimSpec
{
    /// <summary>The tenant.</summary>
    public long ClientId { get; init; }

    /// <summary>The programme code; required, stored upper-cased.</summary>
    public string? ProgramCode { get; init; }

    /// <summary>The tax year; required (<c>None</c> is rejected).</summary>
    public long? TaxYear { get; init; }

    /// <summary>The lifecycle status (default <c>not_assessed</c>).</summary>
    public ClaimStatus Status { get; init; } = ClaimStatus.NotAssessed;

    /// <summary>How we know (default <c>computed</c>).</summary>
    public Provenance Provenance { get; init; } = Provenance.Computed;

    /// <summary>What the engine computed as available: <see cref="ClaimMoney.Of"/> input, default zero.</summary>
    public object? IdentifiedUsd { get; init; }

    /// <summary>What was actually claimed: <see cref="ClaimMoney.Of"/> input, default zero.</summary>
    public object? ClaimedUsd { get; init; }

    /// <summary>What the authority approved: <see cref="ClaimMoney.Of"/> input, default zero.</summary>
    public object? CertifiedUsd { get; init; }

    /// <summary>The year's average headcount.</summary>
    public double? AverageHeadcount { get; init; }

    /// <summary>The frozen base average headcount.</summary>
    public double? BaseAverageHeadcount { get; init; }

    /// <summary>The statutory minimum of net-new jobs.</summary>
    public double? ThresholdJobs { get; init; }

    /// <summary>Whether this is the earliest year held.</summary>
    public bool IsBaseYear { get; init; }

    /// <summary>The legal entity, for programs claimed per entity.</summary>
    public long? EntityId { get; init; }

    /// <summary>The run that identified the figure.</summary>
    public string? IdentifiedRunId { get; init; }

    /// <summary>The assumption set behind the figure.</summary>
    public string? AssumptionSetId { get; init; }

    /// <summary>The rule pack behind the figure.</summary>
    public string? RulePackVersion { get; init; }

    /// <summary>The filing date.</summary>
    public DateOnly? FiledOn { get; init; }

    /// <summary>The filing reference.</summary>
    public string? FilingReference { get; init; }

    /// <summary>Who made the last decision.</summary>
    public string? DecidedBy { get; init; }

    /// <summary>When the last decision was made.</summary>
    public PyDateTime? DecidedAt { get; init; }

    /// <summary>Why the cell was declined (required for a declined cell).</summary>
    public string? DeclineReason { get; init; }

    /// <summary>The record id; <c>null</c> means "omitted" and a new GUID text is generated (Python <c>str(uuid.uuid4())</c>).</summary>
    public string? ClaimId { get; init; }

    /// <summary>When the record took effect; <c>null</c> means "omitted" and the current UTC time is used.</summary>
    public PyDateTime? EffectiveFrom { get; init; }

    /// <summary>When the record was superseded.</summary>
    public PyDateTime? EffectiveTo { get; init; }
}
