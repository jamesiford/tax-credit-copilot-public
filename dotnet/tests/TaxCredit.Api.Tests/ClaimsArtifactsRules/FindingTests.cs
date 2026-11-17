using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Qc;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using Xunit;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class FindingTests
{
    [Fact]
    public async Task Decisions_are_visible_reopening_preserves_history_and_scopes_are_isolated()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        var listed = await Json(await host.Client.GetAsync("/api/findings/1001/2025"));
        var first = listed.GetProperty("findings").EnumerateArray().First();
        var id = first.GetProperty("finding_id").GetString();
        var body = new { client_id = 1001, tax_year = 2025, resolution = "flag", decided_by = "synthetic-reviewer", note = "Investigate" };
        Assert.Equal(HttpStatusCode.OK, (await host.Client.PostAsJsonAsync($"/api/findings/{id}/resolve", body)).StatusCode);
        var decided = await Json(await host.Client.GetAsync("/api/findings/1001/2025"));
        Assert.False(decided.GetProperty("findings").EnumerateArray().Single(f => f.GetProperty("finding_id").GetString() == id)
            .GetProperty("requires_decision").GetBoolean());
        Assert.Equal(HttpStatusCode.OK, (await host.Client.PostAsJsonAsync($"/api/findings/{id}/reopen", body)).StatusCode);
        using var scope = host.App.Services.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IFindingRepository>();
        Assert.Empty(repository.Live(1001, 2025));
        Assert.NotNull(Assert.Single(repository.History(1001, id!)).SupersededAt);
        Assert.Equal(new[] { "resolve", "reopen" }, repository.Audit(1001, id!).Select(a => a.Action));
        Assert.Empty(repository.History(1002, id!));
        Assert.Equal(HttpStatusCode.UnprocessableEntity,
            (await host.Client.PostAsJsonAsync($"/api/findings/{id}/resolve", new { client_id = 1001, tax_year = 2025, resolution = "assign" })).StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await host.Client.GetAsync("/api/findings/1001/2025?state=TN&program_code=GA_JTC")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.GetAsync("/api/findings/1001/2025?program_code=UNKNOWN")).StatusCode);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Ingestion_qc_is_durable_client_year_scoped_and_not_a_finding_resolution()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        using (var scope = host.App.Services.CreateScope())
        {
            using var principal = scope.ServiceProvider.GetRequiredService<IApiPrincipalAccessor>().Push(ApiPrincipal.Anonymous);
            await scope.ServiceProvider.GetRequiredService<IMediator>().Send(new ResolveIngestionQc(1001, 2025, "pp:synthetic-line", "drop", null, "synthetic-reviewer"));
        }
        using (var scope = host.App.Services.CreateScope())
        {
            var qc = scope.ServiceProvider.GetRequiredService<IIngestionQcDecisions>();
            Assert.Single(qc.Snapshot(1001, 2025).Items);
            Assert.True(qc.Snapshot(1002, 2025).IsEmpty);
            Assert.True(qc.Snapshot(1001, 2024).IsEmpty);
            Assert.Empty(scope.ServiceProvider.GetRequiredService<IFindingRepository>().Live(1001));
        }
        await host.App.Services.GetRequiredService<IContractWork>().Reset("P1", CancellationToken.None);
        using var afterReset = host.App.Services.CreateScope();
        Assert.True(afterReset.ServiceProvider.GetRequiredService<IIngestionQcDecisions>().Snapshot(1001, 2025).IsEmpty);
    }

    private static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }
}
