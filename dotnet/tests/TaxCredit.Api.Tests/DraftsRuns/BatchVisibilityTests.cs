using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class BatchVisibilityTests
{
    [Fact]
    public async Task Restricted_reads_narrow_counts_selection_and_liveness_before_paging_and_refuse_whole_batch_mutations()
    {
        var rights = new Rights();
        await using var host = await TestHost.Start(services: services =>
        {
            services.AddSingleton<ISourceReader, Book>();
            services.AddSingleton<IClientAuthorizer>(rights);
        });
        using var accepted = await host.Client.PostAsJsonAsync("/api/v2/run-batches", new { scope = new { kind = "all" }, idempotency_key = "visibility" });
        Assert.Equal(202, (int)accepted.StatusCode);
        var full = await accepted.Content.ReadFromJsonAsync<JsonElement>();
        var id = full.GetProperty("batch_id").GetString();
        host.App.Services.GetRequiredService<IRunBatchRepository>().Create(new RunBatch
        {
            BatchId = "hidden-stale",
            Kind = BatchKind.Calculate,
            ScopeKind = ScopeKind.One,
            ScopeSpec = new(),
            RequestedBy = "synthetic",
            RequestedAt = PyDateTime.FromIsoFormat("2020-01-01T00:00:00+00:00")
        }, [new RunBatchItem { ItemId = "hidden-item", BatchId = "hidden-stale", ClientId = 1002, Seq = 0 }]);
        rights.Allowed.Remove(1002);
        using var detail = await host.Client.GetAsync($"/api/v2/run-batches/{id}");
        Assert.True((int)detail.StatusCode == 200, await detail.Content.ReadAsStringAsync());
        var visible = await detail.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, visible.GetProperty("counts").GetProperty("total").GetInt64());
        var spec = visible.GetProperty("scope_spec");
        Assert.Equal(1, spec.GetProperty("client_count").GetInt64());
        Assert.Equal(1, spec.GetProperty("program_items").GetInt64());
        Assert.Equal(new[] { 1001L }, spec.GetProperty("client_ids").EnumerateArray().Select(e => e.GetInt64()));
        Assert.NotEqual(full.GetProperty("scope_spec").GetProperty("clients_sha256").GetString(), spec.GetProperty("clients_sha256").GetString());
        Assert.Empty(visible.GetProperty("dry_run_summary").EnumerateObject());
        Assert.Empty(visible.GetProperty("degraded").EnumerateArray());
        using var page = await host.Client.GetAsync($"/api/v2/run-batches/{id}/items?offset=1&limit=1");
        var items = await page.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(1, items.GetProperty("total").GetInt64());
        Assert.Empty(items.GetProperty("items").EnumerateArray());
        foreach (var operation in new[] { "cancel", "retry-failed" })
        {
            using var refused = await host.Client.PostAsJsonAsync($"/api/v2/run-batches/{id}/{operation}", new { });
            Assert.Equal(403, (int)refused.StatusCode);
        }
        Assert.False(host.App.Services.GetRequiredService<IRunBatchRepository>().Get(id!)!.CancelRequested);
        using var replay = await host.Client.PostAsJsonAsync("/api/v2/run-batches", new { scope = new { kind = "all" }, idempotency_key = "visibility" });
        Assert.Equal(403, (int)replay.StatusCode);
        rights.Allowed.Clear();
        using var hidden = await host.Client.GetAsync($"/api/v2/run-batches/{id}");
        Assert.Equal(404, (int)hidden.StatusCode);
        using var list = await host.Client.GetAsync("/api/v2/run-batches");
        Assert.Equal(0, (await list.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("total").GetInt64());
    }

    [Fact]
    public async Task Filter_selection_uses_boolean_nearness_one_candidate_and_the_whole_history_for_declining()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<ISourceReader, Book>());
        var claims = host.App.Services.GetRequiredService<IClaimRepository>();
        claims.Record(ProgramClaim.Create(new ClaimSpec
        {
            ClientId = 1001,
            ProgramCode = "GA_JTC",
            TaxYear = 2022,
            Status = ClaimStatus.Assessed,
            AverageHeadcount = 30,
            BaseAverageHeadcount = 20,
            ThresholdJobs = 2,
            IdentifiedUsd = "35000"
        }));
        claims.Record(ProgramClaim.Create(new ClaimSpec
        {
            ClientId = 1001,
            ProgramCode = "GA_JTC",
            TaxYear = 2023,
            Status = ClaimStatus.Assessed,
            AverageHeadcount = 10,
            BaseAverageHeadcount = 20,
            ThresholdJobs = 2
        }));
        using var declining = await Preview(host, new { year = 2023, band = "declining" });
        Assert.Equal(202, (int)declining.StatusCode);
        Assert.Equal(1, (await declining.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("preview").GetProperty("clients").GetInt64());
        using var notNear = await Preview(host, new { near = false });
        Assert.Equal(1, (await notNear.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("preview").GetProperty("clients").GetInt64());
        using var scalar = await Preview(host, new { state = 123 });
        Assert.Equal(422, (int)scalar.StatusCode);
        var queue = host.App.Services.GetRequiredService<IRunBatchRepository>();
        Assert.Equal(0, queue.ListBatches(10, 0).Total);
    }

    private static Task<HttpResponseMessage> Preview(TestHost host, object filter) =>
        host.Client.PostAsJsonAsync("/api/v2/run-batches", new { scope = new { kind = "filter", filter }, dry_run = true });

    private sealed class Rights : IClientAuthorizer
    {
        internal HashSet<long> Allowed { get; } = [1001, 1002];
        public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult(Allowed.Contains(clientId));
    }

    private sealed class Book : ISourceReader
    {
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() => [new(1001, "Synthetic one"), new(1002, "Synthetic two")];
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => new Dictionary<long, IReadOnlyList<string>>
        {
            [1001] = ["GA"],
            [1002] = ["GA"]
        };
    }
}
