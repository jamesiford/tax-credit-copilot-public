using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Xunit;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class ClaimTests
{
    [Fact]
    public async Task Local_http_decisions_name_anonymous_callers_without_misattributing_system_work()
    {
        await using var host = await TestHost.Start();
        var claim = await Json(await host.Client.PostAsJsonAsync("/api/claims", new
        {
            client_id = 5555,
            program_code = "GA_JTC",
            tax_year = 2023,
            status = "assessed",
            provenance = "client_asserted",
        }));
        Assert.Equal("anonymous", claim.GetProperty("decided_by").GetString());
        var engagement = await Json(await host.Client.PutAsJsonAsync("/api/claims/engagement", new
        {
            client_id = 5555,
            program_code = "GA_JTC",
            scope = "in_scope",
        }));
        Assert.Equal("anonymous", engagement.GetProperty("set_by").GetString());
        var finding = await Json(await host.Client.PostAsJsonAsync("/api/findings/synthetic-finding/resolve", new
        {
            client_id = 5555,
            tax_year = 2023,
            resolution = "accept",
        }));
        Assert.Equal("anonymous", finding.GetProperty("decided_by").GetString());
        var named = await Json(await host.Client.PostAsJsonAsync("/api/claims", new
        {
            client_id = 5556,
            program_code = "GA_JTC",
            tax_year = 2023,
            status = "assessed",
            provenance = "client_asserted",
            decided_by = "synthetic-reviewer",
        }));
        Assert.Equal("synthetic-reviewer", named.GetProperty("decided_by").GetString());
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Duplicate_assertion_is_a_conflict_but_transitions_append_and_reopening_is_isolated()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        var assertion = new
        {
            client_id = 5555,
            program_code = "GA_JTC",
            tax_year = 2023,
            status = "assessed",
            provenance = "client_asserted",
            identified_usd = "100.5000",
            claimed_usd = "1.20",
            decided_by = "synthetic-reviewer",
        };
        var created = await host.Client.PostAsJsonAsync("/api/claims", assertion);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        Assert.Equal("100.5000", (await Json(created)).GetProperty("identified_usd").GetString());
        Assert.Equal(HttpStatusCode.Conflict, (await host.Client.PostAsJsonAsync("/api/claims", assertion)).StatusCode);
        foreach (var decision in new[] { new { status = "declined", decline_reason = "Review pending" }, new { status = "assessed", decline_reason = "" } })
        {
            Assert.Equal(HttpStatusCode.OK, (await host.Client.PostAsJsonAsync("/api/claims/cell/5555/GA_JTC/2023/transition", decision)).StatusCode);
        }
        var history = await Json(await host.Client.GetAsync("/api/claims/cell/5555/GA_JTC/2023"));
        Assert.Equal(3, history.GetProperty("history").GetArrayLength());
        Assert.Equal("assessed", history.GetProperty("current").GetProperty("status").GetString());
        var other = await Json(await host.Client.GetAsync("/api/claims/coverage/1001"));
        Assert.DoesNotContain(other.GetProperty("cells").EnumerateArray(), c => c.GetProperty("client_id").GetInt64() != 1001);
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.GetAsync("/api/claims/cell/5555/OTHER/2023")).StatusCode);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Portfolio_preserves_parameter_specific_edges_and_unknown_situation_is_not_zero()
    {
        await using var host = await TestHost.Start();
        host.Client.Timeout = TimeSpan.FromMinutes(5);
        (await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P2" })).EnsureSuccessStatusCode();
        var normal = await Json(await host.Client.GetAsync("/api/v2/portfolio"));
        Assert.Equal(4, normal.GetProperty("total").GetInt32());
        var page = await Json(await host.Client.GetAsync("/api/v2/portfolio?limit=2&offset=1"));
        Assert.Equal(2, page.GetProperty("items").GetArrayLength());
        Assert.True(JsonElement.DeepEquals(normal.GetProperty("items")[1], page.GetProperty("items")[0]));
        var unknown = await Json(await host.Client.GetAsync("/api/v2/portfolio?sort=bogus&order=bogus&status=bogus"));
        Assert.Equal(0, unknown.GetProperty("total").GetInt32());
        Assert.Equal("bogus", unknown.GetProperty("sort").GetString());
        Assert.Equal("asc", unknown.GetProperty("order").GetString());
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await host.Client.GetAsync("/api/v2/portfolio?scope=bogus")).StatusCode);
        var situation = await Json(await host.Client.GetAsync("/api/v2/clients/999999/situation"));
        Assert.False(situation.GetProperty("assessed").GetBoolean());
        Assert.False(situation.TryGetProperty("identified_usd", out _));
    }

    private static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

}
