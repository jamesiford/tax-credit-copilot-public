using System.Net.Http.Json;
using System.Text.Json;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Api.Tests.ReadsCalc;

namespace TaxCredit.Api.Tests.Ai;

public sealed class IntegratedReadTests
{
    [Fact]
    public async Task Ordinary_host_capabilities_read_the_canonical_portfolio_and_stored_headcounts()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var page = await StoredReadTests.Get(host, "/api/v2/portfolio");
        using var book = await host.Client.PostAsJsonAsync("/api/capabilities/book_rank", new { args = new { } });
        book.EnsureSuccessStatusCode();
        var ranked = await book.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(page.GetProperty("total_clients").GetInt32(), ranked.GetProperty("facts").GetProperty("total_clients").GetInt32());
        Assert.Equal(page.GetProperty("items")[0].GetProperty("identified_usd").GetString(),
            ranked.GetProperty("facts").GetProperty("clients")[0].GetProperty("identified_usd").GetString());
        Assert.NotEmpty(page.GetProperty("items")[0].GetProperty("states").EnumerateArray());
        Assert.Equal("Reference Dataset Client", page.GetProperty("items")[0].GetProperty("client_name").GetString());
        var matrix = await StoredReadTests.Get(host, "/api/onezero/matrix/2025?state=GA&account_id=1001&method=min_max");
        using var response = await host.Client.PostAsJsonAsync("/api/capabilities/client_eligibility",
            new { args = new { client_id = 1001, tax_year = 2025 } });
        response.EnsureSuccessStatusCode();
        var result = await response.Content.ReadFromJsonAsync<JsonElement>();
        var facts = result.GetProperty("facts");
        Assert.True(facts.GetProperty("snapshot").GetProperty("calculated").GetBoolean());
        Assert.Equal(matrix.GetProperty("annual_average").GetDouble(), facts.GetProperty("snapshot").GetProperty("average_headcount").GetDouble());
        Assert.Equal(facts.GetProperty("snapshot").GetProperty("run_id").GetString(),
            result.GetProperty("provenance").GetProperty("run_id").GetString());
        Assert.NotNull(result.GetProperty("provenance").GetProperty("trail_sha256").GetString());
    }

    [Theory]
    [InlineData("portfolio")]
    [InlineData("unit")]
    [InlineData("employee")]
    public async Task Ordinary_host_summaries_bind_sibling_page_reads_without_model_access(string page)
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var population = await StoredReadTests.Get(host, "/api/eligibility/2025?account_id=1001&state=GA&limit=1");
        var token = population.GetProperty("rows")[0].GetProperty("record_token").GetString();
        using var response = await host.Client.PostAsJsonAsync("/api/summary",
            new { page, client_id = 1001, tax_year = 2025, worksite_id = "GA_ATL_HQ", record_token = token });
        response.EnsureSuccessStatusCode();
        var frames = StreamEndpointTests.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["brief", "fallback", "done"], frames.Select(frame => frame.Name));
        Assert.Equal(page, frames[0].Data.GetProperty("page").GetString());
        Assert.NotEmpty(frames[1].Data.GetProperty("facts").EnumerateArray());
    }
}
