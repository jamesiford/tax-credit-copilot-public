using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.ReadsCalc.Ingestion;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class IngestionTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Annotations_survive_a_new_scope_reopen_and_disappear_after_a_second_reset()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var initial = await StoredReadTests.Get(host, "/api/ingestion/2025?state=GA&account_id=1001");
        var id = initial.GetProperty("qc").GetProperty("exceptions")[0].GetProperty("exception_id").GetString()!;
        using var written = await host.Client.PostAsJsonAsync($"/api/ingestion/2025/exceptions/{id}/resolve",
            new { resolution = "flag", note = "Synthetic annotation", actor = "synthetic-reviewer" });
        Assert.Equal(200, (int)written.StatusCode);
        using (var reopened = host.App.Services.CreateScope())
        {
            var annotations = reopened.ServiceProvider.GetRequiredService<QcAnnotations>().Resolutions(1001);
            Assert.Contains(annotations.Items, row => row.Key == id && Equals(row.Value["resolution"], "flag"));
        }
        var annotated = await StoredReadTests.Get(host, "/api/ingestion/2025?state=GA&account_id=1001");
        Assert.Equal("flag", annotated.GetProperty("qc").GetProperty("exceptions")[0].GetProperty("resolution").GetProperty("resolution").GetString());
        using var reopen = await host.Client.PostAsJsonAsync($"/api/ingestion/2025/exceptions/{id}/resolve", new { resolution = "reopen" });
        Assert.Equal(200, (int)reopen.StatusCode);
        var withdrawn = await StoredReadTests.Get(host, "/api/ingestion/2025?state=GA&account_id=1001");
        Assert.Equal(JsonValueKind.Null, withdrawn.GetProperty("qc").GetProperty("exceptions")[0].GetProperty("resolution").ValueKind);
        await RuntimeRequests.Reset(host);
        using var resetScope = host.App.Services.CreateScope();
        Assert.Empty(resetScope.ServiceProvider.GetRequiredService<QcAnnotations>().Resolutions(1001).Items);
    }

    [Fact]
    public async Task Source_browsing_keeps_the_filtered_total_and_sorts_before_paging()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var first = await StoredReadTests.Get(host, "/api/ingestion/2025/rows?limit=1&sort=hours&order=desc");
        var second = await StoredReadTests.Get(host, "/api/ingestion/2025/rows?limit=1&sort=hours&order=desc&offset=1");
        Assert.Equal(3154, first.GetProperty("total").GetInt32());
        Assert.Equal(first.GetProperty("total").GetInt32(), second.GetProperty("total").GetInt32());
        Assert.True(first.GetProperty("rows")[0].GetProperty("Hours_Worked").GetDouble()
            >= second.GetProperty("rows")[0].GetProperty("Hours_Worked").GetDouble());
    }
}
