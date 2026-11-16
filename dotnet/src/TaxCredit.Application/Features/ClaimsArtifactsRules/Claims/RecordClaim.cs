using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Records an attributed assertion without confusing duplicate requests with later evidence.</summary>
public sealed record RecordClaim(JsonElement Body, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class RecordClaimHandler(IClaimRepository repository, RuleLibrary rules, IClock clock, IIdSource ids)
    : IRequestHandler<RecordClaim, object>
{
    public ValueTask<object> Handle(RecordClaim request, CancellationToken cancellationToken)
    {
        var claim = Build(request);
        var existing = repository.Current(claim.ClientId, claim.ProgramCode, claim.TaxYear);
        if (existing is not null && Equivalent(existing, claim))
        {
            throw new FeatureRefusalException(409, "An identical claim is already recorded; use transition to change its decision.");
        }
        return ValueTask.FromResult<object>(repository.Record(claim).ToDict());
    }

    private ProgramClaim Build(RecordClaim request)
    {
        var b = request.Body;
        var code = FeatureValues.Text(b, "program_code")!;
        var average = FeatureValues.Number(b, "average_headcount");
        var threshold = FeatureValues.Number(b, "threshold_jobs");
        if (threshold is null && average is not null && rules.PackFileFor(code) is { } file)
        {
            var pack = rules.LoadPack(file);
            if (pack.TryGetValue("thresholds", out var value) && value is PyDict thresholds
                && thresholds.TryGetValue("minimum_new_jobs", out var minimum) && minimum is not null)
            {
                threshold = Convert.ToDouble(minimum, System.Globalization.CultureInfo.InvariantCulture);
            }
        }
        return ProgramClaim.Create(new ClaimSpec
        {
            ClientId = FeatureValues.Whole(b, "client_id"),
            ProgramCode = code,
            TaxYear = FeatureValues.Whole(b, "tax_year"),
            Status = ClaimEnumExtensions.StatusFromValue(FeatureValues.Text(b, "status")!),
            Provenance = ClaimEnumExtensions.ProvenanceFromValue(FeatureValues.Text(b, "provenance")!),
            IdentifiedUsd = FeatureValues.Money(b, "identified_usd") ?? PyDecimalOps.Zero,
            ClaimedUsd = FeatureValues.Money(b, "claimed_usd") ?? PyDecimalOps.Zero,
            CertifiedUsd = FeatureValues.Money(b, "certified_usd") ?? PyDecimalOps.Zero,
            AverageHeadcount = average,
            BaseAverageHeadcount = FeatureValues.Number(b, "base_average_headcount"),
            ThresholdJobs = threshold,
            EntityId = b.TryGetProperty("entity_id", out var entity) && entity.ValueKind != JsonValueKind.Null ? FeatureValues.Whole(b, "entity_id") : null,
            FilingReference = FeatureValues.Text(b, "filing_reference"),
            DeclineReason = FeatureValues.Text(b, "decline_reason"),
            IdentifiedRunId = FeatureValues.Text(b, "identified_run_id"),
            AssumptionSetId = FeatureValues.Text(b, "assumption_set_id"),
            RulePackVersion = FeatureValues.Text(b, "rule_pack_version"),
            DecidedBy = request.Actor,
            ClaimId = ids.NewId().ToString(),
            EffectiveFrom = FeatureValues.Now(clock),
        });
    }

    private static bool Equivalent(ProgramClaim left, ProgramClaim right) =>
        left.ToSpec() with { ClaimId = null, EffectiveFrom = null, EffectiveTo = null, DecidedAt = null }
        == right.ToSpec() with { ClaimId = null, EffectiveFrom = null, EffectiveTo = null, DecidedAt = null };
}
