using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>The wire shape of a claim.</summary>
public sealed partial record ProgramClaim
{
    /// <summary>
    /// Python <c>to_dict()</c>: the wire shape, keys in Python's order. Money is a string (a claim figure must not meet a float);
    /// <c>variance_usd</c> is <c>None</c> in a base year, where the subtraction would be a number about our coverage.
    /// </summary>
    /// <returns>An ordered tree of <c>null</c>, bool, long, double, string values.</returns>
    public PyDict ToDict() => new PyDict()
        .Add("claim_id", ClaimId)
        .Add("client_id", ClientId)
        .Add("entity_id", EntityId)
        .Add("program_code", ProgramCode)
        .Add("tax_year", TaxYear)
        .Add("status", Status.Value())
        .Add("provenance", Provenance.Value())
        .Add("provenance_verified", Provenance.Verified())
        .Add("identified_usd", IdentifiedUsd.ToString())
        .Add("claimed_usd", ClaimedUsd.ToString())
        .Add("certified_usd", CertifiedUsd.ToString())
        .Add("variance_usd", IsBaseYear ? null : VarianceUsd.ToString())
        .Add("variance_is_computable", VarianceIsComputable)
        .Add("opportunity_usd", OpportunityUsd.ToString())
        .Add("average_headcount", AverageHeadcount)
        .Add("base_average_headcount", BaseAverageHeadcount)
        .Add("threshold_jobs", ThresholdJobs)
        .Add("is_base_year", IsBaseYear)
        .Add("net_new_jobs", NetNewJobs)
        .Add("jobs_to_threshold", JobsToThreshold)
        .Add("jobs_margin", JobsMargin)
        .Add("near_threshold", NearThreshold)
        .Add("priority_band", PriorityBand.Value())
        .Add("priority_rank", PriorityBand.Rank())
        .Add("outcome", Outcome.Value())
        .Add("is_exposure", IsExposure)
        .Add("identified_run_id", IdentifiedRunId)
        .Add("assumption_set_id", AssumptionSetId)
        .Add("rule_pack_version", RulePackVersion)
        .Add("filed_on", FiledOn is { } filed ? PyDateFormat(filed) : null)
        .Add("filing_reference", FilingReference)
        .Add("decided_by", DecidedBy)
        .Add("decided_at", DecidedAt?.IsoFormat())
        .Add("decline_reason", DeclineReason)
        .Add("effective_from", EffectiveFrom.IsoFormat())
        .Add("effective_to", EffectiveTo?.IsoFormat());

    /// <summary>Python <c>date.isoformat()</c>.</summary>
    /// <param name="date">The date.</param>
    /// <returns><c>YYYY-MM-DD</c>.</returns>
    internal static string PyDateFormat(DateOnly date) =>
        string.Create(System.Globalization.CultureInfo.InvariantCulture, $"{date.Year:D4}-{date.Month:D2}-{date.Day:D2}");
}
