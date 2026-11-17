using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.ClaimsArtifactsRules;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class BatchFootprintTests
{
    [Fact]
    public async Task An_explicit_program_and_no_state_filter_never_reads_the_footprint()
    {
        var book = new PortfolioFootprintTests.CountingBook(12);
        await using var host = await Start(book);
        foreach (var scope in new object[] { new { kind = "all" }, new { kind = "list", client_ids = new[] { 1001, 1002 } },
            new { kind = "filter", filter = new { unassessed = true } } })
        {
            using var response = await Preview(host, new { scope, program_code = "GA_JTC" });
            Assert.Equal(202, (int)response.StatusCode);
        }
        Assert.Empty(book.Asked);
        Assert.Equal(0, book.WholeBookReads);
    }

    [Fact]
    public async Task Programs_are_derived_from_the_footprint_of_the_selected_clients_only()
    {
        var book = new PortfolioFootprintTests.CountingBook(12);
        await using var host = await Start(book);
        using var named = await Preview(host, new { scope = new { kind = "list", client_ids = new[] { 1003, 1001 } } });
        Assert.Equal(202, (int)named.StatusCode);
        Assert.Equal(new long[] { 1001, 1003 }, Assert.Single(book.Asked).Order());
        book.Asked.Clear();
        using var all = await Preview(host, new { scope = new { kind = "all" } });
        Assert.Equal(202, (int)all.StatusCode);
        Assert.Equal(Enumerable.Range(1001, 12).Select(i => (long)i), Assert.Single(book.Asked).Order());
        Assert.Equal(0, book.WholeBookReads);
    }

    [Fact]
    public async Task A_state_filter_reads_the_candidates_once_and_reuses_them_for_programs()
    {
        var book = new PortfolioFootprintTests.CountingBook(12);
        await using var host = await Start(book);
        using var response = await Preview(host, new { scope = new { kind = "filter", filter = new { state = "GA" } } });
        Assert.Equal(202, (int)response.StatusCode);
        Assert.Single(book.Asked);
        Assert.Equal(12, (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("preview").GetProperty("clients").GetInt64());
        book.Asked.Clear();
        using var withProgram = await Preview(host, new { scope = new { kind = "filter", filter = new { state = "GA" } }, program_code = "GA_JTC" });
        Assert.Equal(202, (int)withProgram.StatusCode);
        Assert.Single(book.Asked);
    }

    [Theory]
    [InlineData("footprint_off")]
    [InlineData("footprint_too_large")]
    [InlineData("footprint_timeout")]
    public async Task A_footprint_the_planner_needs_but_cannot_have_is_a_typed_actionable_refusal(string code)
    {
        var book = new PortfolioFootprintTests.CountingBook(3) { Refusal = new SourceFootprintUnavailable(code, "the reason", "set PORTFOLIO_FOOTPRINT_MODE") };
        await using var host = await Start(book);
        foreach (var body in new object[] { new { scope = new { kind = "all" } },
            new { scope = new { kind = "filter", filter = new { state = "GA" } }, program_code = "GA_JTC" } })
        {
            using var response = await Preview(host, body);
            Assert.Equal(503, (int)response.StatusCode);
            var error = (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail");
            Assert.Equal(code, error.GetProperty("code").GetString());
            Assert.Equal("source_sql", error.GetProperty("dependency").GetString());
            Assert.Equal("the reason", error.GetProperty("reason").GetString());
            Assert.Equal("set PORTFOLIO_FOOTPRINT_MODE", error.GetProperty("remedy").GetString());
        }
        using var fine = await Preview(host, new { scope = new { kind = "all" }, program_code = "GA_JTC" });
        Assert.Equal(202, (int)fine.StatusCode);
    }

    private static Task<TestHost> Start(ISourceReader book) =>
        TestHost.Start(services: services => services.AddSingleton<ISourceReader>(book));

    private static Task<HttpResponseMessage> Preview(TestHost host, object body)
    {
        var fields = JsonSerializer.SerializeToElement(body).EnumerateObject().ToDictionary(p => p.Name, p => (object)p.Value);
        fields["dry_run"] = true;
        return host.Client.PostAsJsonAsync("/api/v2/run-batches", fields);
    }
}
