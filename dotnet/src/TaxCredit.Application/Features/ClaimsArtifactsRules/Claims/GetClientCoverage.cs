using TaxCredit.Application.Messaging;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Claims;

/// <summary>Reads the exact cells whose totals are displayed.</summary>
public sealed record GetClientCoverage(long ClientId, string? ProgramCode, IReadOnlyList<long> TaxYears) : IQuery<object>;

internal sealed class GetClientCoverageHandler(IClaimRepository repository) : IRequestHandler<GetClientCoverage, object>
{
    public ValueTask<object> Handle(GetClientCoverage request, CancellationToken cancellationToken)
    {
        var years = request.TaxYears.Count == 0 ? null : request.TaxYears;
        var claims = repository.Coverage(request.ClientId, request.ProgramCode is { } code ? [code] : null, years);
        var engagements = repository.Engagements(request.ClientId);
        return ValueTask.FromResult<object>(new
        {
            client_id = request.ClientId,
            tax_years = years,
            cells = Coverage.Matrix(claims, engagements.ToDictionary(e => e.ProgramCode, e => (EngagementScope?)e.Scope, StringComparer.Ordinal)),
            totals = Coverage.Totals(claims),
            program_totals = Coverage.TotalsByProgram(claims),
            engagements = engagements.Select(e => e.ToDict()),
        });
    }
}
