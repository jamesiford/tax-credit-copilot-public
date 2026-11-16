using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Routing;
using TaxCredit.Api.Endpoints;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Api.Tests.Framework;

public sealed class RuntimeProbeEndpoints : IEndpointGroup
{
    public void Map(IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/me", async (IApiPrincipalAccessor principal) =>
        {
            var before = principal.Current;
            await Task.Yield();
            Assert.Same(before, principal.Current);
            return before!.ToIdentityBody();
        });
        endpoints.MapGet("/api/v2/clients/{client_id}/units", Observe);
    }

    private static IResult Observe(long client_id, IRunManifestRepository manifests, ISourceReader source,
        ISourceCatalogue catalogue, IApiPrincipalAccessor principal, IRuntimeConfiguration settings)
    {
        var accounts = source.ListAccounts();
        return accounts.Any(a => a.AccountId == client_id) ? Results.Json(new
        {
            manifests = manifests.Count(),
            accounts = accounts.Select(a => a.AccountId),
            rows = catalogue.PayrollScope(client_id).TotalRows,
            principal = principal.Current!.Oid,
            source = settings.Get("DATA_SOURCE"),
            second_reviewer = settings.Get("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER"),
        }) : Results.NotFound(new { detail = "Unknown synthetic account." });
    }
}
