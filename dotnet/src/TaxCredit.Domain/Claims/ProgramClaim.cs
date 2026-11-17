using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>
/// One cell of the coverage matrix: client x program x tax year (Python <c>ProgramClaim</c>, a frozen dataclass).
/// </summary>
/// <remarks>
/// Immutable. A status change produces a NEW record (<see cref="TransitionTo"/>) and never updates in place: the audit question is
/// "what did you believe on the day you filed?". Money is normalised to exact decimals once, in <see cref="Create"/>, so every
/// comparison downstream is decimal-to-decimal. Headcounts are floats: an int passed where Python would keep an int (and so print
/// <c>1</c> rather than <c>1.0</c>) is not modelled.
/// </remarks>
public sealed partial record ProgramClaim
{
    private ProgramClaim()
    {
    }

    /// <summary>The tenant.</summary>
    public long ClientId { get; private init; }

    /// <summary>The programme code, upper-cased by Python's <c>str.upper()</c> (Unicode 15 tables).</summary>
    public string ProgramCode { get; private init; } = string.Empty;

    /// <summary>The tax year.</summary>
    public long TaxYear { get; private init; }

    /// <summary>The lifecycle status.</summary>
    public ClaimStatus Status { get; private init; }

    /// <summary>How we know the figures.</summary>
    public Provenance Provenance { get; private init; }

    /// <summary>What the engine computed as available.</summary>
    public PyDecimal IdentifiedUsd { get; private init; }

    /// <summary>What was actually claimed.</summary>
    public PyDecimal ClaimedUsd { get; private init; }

    /// <summary>What the authority approved.</summary>
    public PyDecimal CertifiedUsd { get; private init; }

    /// <summary>The year's average headcount.</summary>
    public double? AverageHeadcount { get; private init; }

    /// <summary>The frozen base average headcount.</summary>
    public double? BaseAverageHeadcount { get; private init; }

    /// <summary>The statutory minimum of net-new jobs.</summary>
    public double? ThresholdJobs { get; private init; }

    /// <summary>Whether this is the earliest year held, so there is no prior year to measure net-new against.</summary>
    public bool IsBaseYear { get; private init; }

    /// <summary>The legal entity, for programs claimed per entity.</summary>
    public long? EntityId { get; private init; }

    /// <summary>The run that identified the figure.</summary>
    public string? IdentifiedRunId { get; private init; }

    /// <summary>The assumption set behind the figure.</summary>
    public string? AssumptionSetId { get; private init; }

    /// <summary>The rule pack behind the figure.</summary>
    public string? RulePackVersion { get; private init; }

    /// <summary>The filing date.</summary>
    public DateOnly? FiledOn { get; private init; }

    /// <summary>The filing reference.</summary>
    public string? FilingReference { get; private init; }

    /// <summary>Who made the last decision.</summary>
    public string? DecidedBy { get; private init; }

    /// <summary>When the last decision was made.</summary>
    public PyDateTime? DecidedAt { get; private init; }

    /// <summary>Why the cell was declined.</summary>
    public string? DeclineReason { get; private init; }

    /// <summary>The record id.</summary>
    public string? ClaimId { get; private init; }

    /// <summary>When the record took effect.</summary>
    public PyDateTime EffectiveFrom { get; private init; }

    /// <summary>When the record was superseded (<c>null</c> while it is the live one).</summary>
    public PyDateTime? EffectiveTo { get; private init; }

    /// <summary>Python <c>cell_key</c>: the coverage-matrix grain.</summary>
    public (long ClientId, string ProgramCode, long TaxYear) CellKey => (ClientId, ProgramCode, TaxYear);

    /// <summary>Python <c>is_current</c>.</summary>
    public bool IsCurrent => EffectiveTo is null;

    /// <summary>Python <c>ProgramClaim(...)</c> including <c>__post_init__</c>: validates, then normalises money and the programme code.</summary>
    /// <param name="spec">The field values.</param>
    /// <returns>The validated claim.</returns>
    /// <exception cref="ClaimError">When the programme code or tax year is missing, or a declined cell has no reason.</exception>
    /// <exception cref="PyInvalidOperation">When a money value is not a decimal literal.</exception>
    public static ProgramClaim Create(ClaimSpec spec)
    {
        ArgumentNullException.ThrowIfNull(spec);
        if (string.IsNullOrEmpty(spec.ProgramCode))
        {
            throw new ClaimError("program_code is required");
        }

        if (spec.TaxYear is not { } taxYear)
        {
            throw new ClaimError(
                "tax_year is required: statute is year-scoped [ADR-005], so a claim without a year cannot be checked against any rules");
        }

        // Python normalises money before it checks the decline reason, so a bad amount wins over a missing reason.
        var identified = ClaimMoney.Of(spec.IdentifiedUsd);
        var claimed = ClaimMoney.Of(spec.ClaimedUsd);
        var certified = ClaimMoney.Of(spec.CertifiedUsd);
        var code = PyStr.Upper(spec.ProgramCode);
        if (spec.Status == ClaimStatus.Declined && PyStr.Strip(spec.DeclineReason ?? string.Empty).Length == 0)
        {
            // Mandatory by design: "We take the R&D credit instead" is durable knowledge; without it every later run re-proposes it.
            throw new ClaimError(string.Create(CultureInfo.InvariantCulture, $"decline_reason is required when status is declined ({code} TY{taxYear})"));
        }

        return new ProgramClaim
        {
            ClientId = spec.ClientId,
            ProgramCode = code,
            TaxYear = taxYear,
            Status = spec.Status,
            Provenance = spec.Provenance,
            IdentifiedUsd = identified,
            ClaimedUsd = claimed,
            CertifiedUsd = certified,
            AverageHeadcount = spec.AverageHeadcount,
            BaseAverageHeadcount = spec.BaseAverageHeadcount,
            ThresholdJobs = spec.ThresholdJobs,
            IsBaseYear = spec.IsBaseYear,
            EntityId = spec.EntityId,
            IdentifiedRunId = spec.IdentifiedRunId,
            AssumptionSetId = spec.AssumptionSetId,
            RulePackVersion = spec.RulePackVersion,
            FiledOn = spec.FiledOn,
            FilingReference = spec.FilingReference,
            DecidedBy = spec.DecidedBy,
            DecidedAt = spec.DecidedAt,
            DeclineReason = spec.DeclineReason,
            ClaimId = spec.ClaimId ?? Guid.NewGuid().ToString(),
            EffectiveFrom = spec.EffectiveFrom ?? PyDateTime.UtcNow(),
            EffectiveTo = spec.EffectiveTo,
        };
    }

    /// <summary>The field values of this claim as a <see cref="ClaimSpec"/> (Python <c>dataclasses.replace</c> re-runs the constructor with them).</summary>
    /// <returns>A spec whose <see cref="Create"/> reproduces this claim.</returns>
    public ClaimSpec ToSpec() => new()
    {
        ClientId = ClientId,
        ProgramCode = ProgramCode,
        TaxYear = TaxYear,
        Status = Status,
        Provenance = Provenance,
        IdentifiedUsd = IdentifiedUsd,
        ClaimedUsd = ClaimedUsd,
        CertifiedUsd = CertifiedUsd,
        AverageHeadcount = AverageHeadcount,
        BaseAverageHeadcount = BaseAverageHeadcount,
        ThresholdJobs = ThresholdJobs,
        IsBaseYear = IsBaseYear,
        EntityId = EntityId,
        IdentifiedRunId = IdentifiedRunId,
        AssumptionSetId = AssumptionSetId,
        RulePackVersion = RulePackVersion,
        FiledOn = FiledOn,
        FilingReference = FilingReference,
        DecidedBy = DecidedBy,
        DecidedAt = DecidedAt,
        DeclineReason = DeclineReason,
        ClaimId = ClaimId,
        EffectiveFrom = EffectiveFrom,
        EffectiveTo = EffectiveTo,
    };
}
