using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Runs the certified multi-year sweep, preserving decisions as evidence is refreshed.</summary>
public sealed record AssessClient(long ClientId, string? ProgramCode, IReadOnlyList<long> TaxYears, string Actor)
    : ICommand<object>, IRequirePolicy
{
    /// <summary>Preserves the documented F-14 valid-request exception already enforced by the host.</summary>
    public Policy Policy => Policy.Open;
}

internal sealed class AssessClientHandler(IClientPayrollSource payroll, ClientAssessment assessment,
    IClaimRepository repository, FiscalSource fiscal, IClock clock, IIdSource ids) : IRequestHandler<AssessClient, object>
{
    public ValueTask<object> Handle(AssessClient request, CancellationToken cancellationToken)
    {
        if (request.ClientId <= 0) { throw new FeatureRefusalException(422, "client_id must be positive"); }
        var rows = payroll.LoadPayPeriods(request.ClientId);
        if (rows.Count == 0) { throw new FeatureRefusalException(404, "No payroll for this client in the active data source."); }
        var sink = new AssessmentSink(repository, clock, ids);
        var result = assessment.Assess(request.ClientId, rows, request.ProgramCode, request.TaxYears, request.Actor, sink);
        var cells = result.Assessed.Select(c =>
        {
            var stored = sink.Recorded[c.CellKey];
            var window = fiscal.FiscalWindowForStateYear(request.ClientId, c.ProgramCode, c.TaxYear);
            return stored.ToDict().Add("fiscal_window", new PyDict().Add("assumed", window?.Assumed ?? false)
                .Add("note", window?.Assumed == true ? window.Note : ""));
        }).ToArray();
        return ValueTask.FromResult<object>(new { assessed = cells, declined = result.Declined, years = result.Years, states = result.States });
    }

    // The certified initial-claim factory predates the host clock seam; normalize identity only, never its calculated fields.
    private sealed class AssessmentSink(IClaimRepository repository, IClock clock, IIdSource ids) : IClaimSink
    {
        internal Dictionary<(long, string, long), ProgramClaim> Recorded { get; } = [];
        public ProgramClaim? Current(long clientId, string programCode, long taxYear) => repository.Current(clientId, programCode, taxYear);
        public void Record(ProgramClaim claim)
        {
            var prior = Current(claim.ClientId, claim.ProgramCode, claim.TaxYear);
            if (prior is null || prior.Status == ClaimStatus.NotAssessed)
            {
                claim = ProgramClaim.Create(claim.ToSpec() with { ClaimId = ids.NewId().ToString(), EffectiveFrom = FeatureValues.Now(clock) });
            }
            Recorded[claim.CellKey] = repository.Record(claim);
        }
    }
}
