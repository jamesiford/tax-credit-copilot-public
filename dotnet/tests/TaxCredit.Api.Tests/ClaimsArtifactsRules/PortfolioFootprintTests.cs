using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class PortfolioFootprintTests
{
    [Fact]
    public async Task A_page_of_ten_asks_the_source_for_ten_clients_and_nothing_else()
    {
        var book = new CountingBook(25);
        await using var host = await TestHost.Start(services: services => services.AddSingleton<ISourceReader>(book));
        var first = await Json(await host.Client.GetAsync("/api/v2/portfolio?limit=10"));
        var ids = Ids(first);
        Assert.Equal(10, ids.Length);
        Assert.Equal(25, first.GetProperty("total").GetInt32());
        Assert.Equal(ids.Order(), Assert.Single(book.Asked).Order());
        Assert.Equal(0, book.WholeBookReads);
        Assert.All(first.GetProperty("items").EnumerateArray(), row =>
            Assert.Equal(new[] { "GA" }, row.GetProperty("states").EnumerateArray().Select(s => s.GetString())));
        Assert.Empty(first.GetProperty("degraded").EnumerateArray());

        book.Asked.Clear();
        var second = await Json(await host.Client.GetAsync("/api/v2/portfolio?limit=10&offset=10"));
        Assert.Equal(Ids(second).Order(), Assert.Single(book.Asked).Order());
        Assert.Empty(Ids(second).Intersect(ids));

        book.Asked.Clear();
        _ = await Json(await host.Client.GetAsync("/api/v2/portfolio?limit=10&offset=500"));
        Assert.Empty(book.Asked);
    }

    [Theory]
    [InlineData("footprint_off")]
    [InlineData("footprint_too_large")]
    [InlineData("footprint_timeout")]
    public async Task A_footprint_the_source_will_not_read_degrades_the_page_instead_of_failing_it(string code)
    {
        var book = new CountingBook(12) { Refusal = new SourceFootprintUnavailable(code, "the reason", "set PORTFOLIO_FOOTPRINT_MODE") };
        await using var host = await TestHost.Start(services: services => services.AddSingleton<ISourceReader>(book));
        using var response = await host.Client.GetAsync("/api/v2/portfolio?limit=5");
        Assert.Equal(200, (int)response.StatusCode);
        var page = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal(5, page.GetProperty("items").GetArrayLength());
        Assert.All(page.GetProperty("items").EnumerateArray(), row =>
        {
            Assert.Empty(row.GetProperty("states").EnumerateArray());
            Assert.Empty(row.GetProperty("priceable_states").EnumerateArray());
        });
        var entry = Assert.Single(page.GetProperty("degraded").EnumerateArray());
        Assert.Equal(new[] { "dependency", "impact", "remedy" }, entry.EnumerateObject().Select(p => p.Name));
        Assert.Equal("source_sql", entry.GetProperty("dependency").GetString());
        Assert.Equal(SourceFootprintUnavailable.ImpactText, entry.GetProperty("impact").GetString());
        Assert.Equal("set PORTFOLIO_FOOTPRINT_MODE", entry.GetProperty("remedy").GetString());
    }

    [Fact]
    public void The_page_only_check_rejects_a_read_of_the_whole_book_or_a_short_page()
    {
        var page = new long[] { 3, 4, 5 };
        Assert.True(Agrees(page, page));
        Assert.False(Agrees(page, Enumerable.Range(1, 25).Select(i => (long)i).ToArray()));
        Assert.False(Agrees(page, [3, 4]));
        Assert.False(Agrees(page, [3, 4, 5, 6]));
        Assert.False(Agrees(page, []));

        static bool Agrees(long[] returned, long[] asked) => returned.Order().SequenceEqual(asked.Order());
    }

    private static long[] Ids(JsonElement page) =>
        page.GetProperty("items").EnumerateArray().Select(row => row.GetProperty("client_id").GetInt64()).ToArray();

    private static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        Assert.Equal(200, (int)response.StatusCode);
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    internal sealed class CountingBook(int count) : ISourceReader
    {
        internal List<long[]> Asked { get; } = [];
        internal int WholeBookReads { get; private set; }
        internal SourceFootprintUnavailable? Refusal { get; set; }
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() =>
            Enumerable.Range(1, count).Select(i => new SourceAccount(1000 + i, $"Synthetic {i:00}")).ToArray();
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint()
        {
            WholeBookReads++;
            return ListAccounts().ToDictionary(a => a.AccountId, _ => (IReadOnlyList<string>)["GA"]);
        }
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint(IReadOnlyCollection<long> accountIds)
        {
            Asked.Add(accountIds.ToArray());
            return Refusal is { } refusal ? throw refusal : accountIds.ToDictionary(id => id, _ => (IReadOnlyList<string>)["GA"]);
        }
    }
}
