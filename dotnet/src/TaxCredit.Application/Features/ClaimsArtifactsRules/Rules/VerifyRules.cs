using System.Globalization;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>Records a practitioner decision separately from the rule document itself.</summary>
public sealed record VerifyRules(string Code, string Actor, string? Note) : ICommand<object>, IRequirePolicy
{
    /// <summary>Preserves the named F-14 valid-request exception already classified by the host.</summary>
    public Policy Policy => Policy.Open;
}

internal sealed class VerifyRulesHandler(RuleCatalogue catalogue, PackValidator validator, IClock clock) : IRequestHandler<VerifyRules, object>
{
    public ValueTask<object> Handle(VerifyRules request, CancellationToken cancellationToken)
    {
        var code = request.Code.ToUpperInvariant();
        var pack = catalogue.Packs().FirstOrDefault(p => RuleCatalogue.Get(RuleCatalogue.Map(p.Pack, "credit"), "code") as string == code);
        if (pack.Pack is null) { throw new FeatureRefusalException(404, "Unknown rule pack code."); }
        if (!validator.ValidateDocument(pack.Pack, pack.File, "base").Ok)
        {
            throw new FeatureRefusalException(422, "A structurally invalid pack cannot receive practitioner sign-off.");
        }
        var verification = new PyDict().Add("verified_by", request.Actor)
            .Add("verified_at", clock.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)).Add("note", request.Note);
        catalogue.Verify(code, verification, request.Actor, FeatureValues.Now(clock));
        return ValueTask.FromResult<object>(new PyDict().Add("code", code).Add("verification", verification));
    }
}
