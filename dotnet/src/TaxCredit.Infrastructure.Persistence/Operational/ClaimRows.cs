using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

internal static class ClaimRows
{
    internal static readonly string[] Columns =
    [
        "claim_id", "client_id", "entity_id", "program_code", "tax_year", "status", "provenance",
        "identified_usd", "claimed_usd", "certified_usd", "average_headcount", "base_average_headcount",
        "threshold_jobs", "is_base_year", "identified_run_id", "assumption_set_id", "rule_pack_version",
        "filed_on", "filing_reference", "decided_by", "decided_at", "decline_reason", "effective_from", "effective_to",
    ];

    internal static readonly string[] EngagementColumns =
    [
        "client_id", "program_code", "scope", "effective_from", "effective_to", "note", "set_by", "set_at",
    ];

    internal static string Select => "SELECT " + string.Join(", ", Columns) + " FROM {ops.program_claim}";

    internal static object?[] Values(SqlSession session, ProgramClaim claim) =>
    [
        claim.ClaimId, claim.ClientId, claim.EntityId, claim.ProgramCode, claim.TaxYear, claim.Status.Value(),
        claim.Provenance.Value(), claim.IdentifiedUsd.ToString(), claim.ClaimedUsd.ToString(), claim.CertifiedUsd.ToString(),
        claim.AverageHeadcount, claim.BaseAverageHeadcount, claim.ThresholdJobs, claim.IsBaseYear, claim.IdentifiedRunId,
        claim.AssumptionSetId, claim.RulePackVersion, claim.FiledOn, claim.FilingReference, claim.DecidedBy,
        OpsRow.Timestamp(session, claim.DecidedAt), claim.DeclineReason, OpsRow.EffectiveDate(session, claim.EffectiveFrom), OpsRow.EffectiveDate(session, claim.EffectiveTo),
    ];

    internal static ProgramClaim Claim(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return ProgramClaim.Create(new ClaimSpec
        {
            ClaimId = r.Required("claim_id"),
            ClientId = r.Long("client_id"),
            EntityId = r.OptionalLong("entity_id"),
            ProgramCode = r.Required("program_code"),
            TaxYear = r.Long("tax_year"),
            Status = ClaimEnumExtensions.StatusFromValue(r.Required("status")),
            Provenance = ClaimEnumExtensions.ProvenanceFromValue(r.Required("provenance")),
            IdentifiedUsd = PyDecimal.Parse(r.Required("identified_usd")),
            ClaimedUsd = PyDecimal.Parse(r.Required("claimed_usd")),
            CertifiedUsd = PyDecimal.Parse(r.Required("certified_usd")),
            AverageHeadcount = r.Number("average_headcount"),
            BaseAverageHeadcount = r.Number("base_average_headcount"),
            ThresholdJobs = r.Number("threshold_jobs"),
            IsBaseYear = r.Bool("is_base_year"),
            IdentifiedRunId = r.Text("identified_run_id"),
            AssumptionSetId = r.Text("assumption_set_id"),
            RulePackVersion = r.Text("rule_pack_version"),
            FiledOn = r.Day("filed_on"),
            FilingReference = r.Text("filing_reference"),
            DecidedBy = r.Text("decided_by"),
            DecidedAt = r.Instant("decided_at"),
            DeclineReason = r.Text("decline_reason"),
            EffectiveFrom = r.Instant("effective_from"),
            EffectiveTo = r.Instant("effective_to"),
        });
    }

    internal static ProgramEngagement Engagement(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new ProgramEngagement
        {
            ClientId = r.Long("client_id"),
            ProgramCode = r.Required("program_code"),
            Scope = ClaimEnumExtensions.ScopeFromValue(r.Required("scope")),
            EffectiveFrom = r.Instant("effective_from")!.Value,
            EffectiveTo = r.Instant("effective_to"),
            Note = r.Text("note"),
            SetBy = r.Text("set_by"),
            SetAt = r.Instant("set_at"),
        };
    }
}
