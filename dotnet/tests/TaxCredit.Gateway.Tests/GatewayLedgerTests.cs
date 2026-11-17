using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayLedgerTests(GatewayFixture host) : IClassFixture<GatewayFixture>, IAsyncLifetime
{
    public Task InitializeAsync() => host.Reset();
    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task Verification_uses_only_trusted_successful_facts_from_this_person_and_conversation()
    {
        var token = await host.Token();
        await host.Invoke("client_situation", token, new() { ["client_id"] = 1001 }, "facts-here");
        var matching = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 1001" }, "facts-here");
        Assert.Equal("pass", matching["facts"]!["status"]!.ToString());
        var wrong = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 9999" }, "facts-here");
        Assert.Equal("rejected", wrong["facts"]!["status"]!.ToString());
        var otherConversation = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 1001" }, "elsewhere");
        Assert.Equal("rejected", otherConversation["facts"]!["status"]!.ToString());
        var otherPerson = await host.Invoke("verify_figures", await host.Token(GatewayFixture.Writer),
            new() { ["draft_text"] = "Client 1001" }, "facts-here");
        Assert.Equal("rejected", otherPerson["facts"]!["status"]!.ToString());
        using var missing = await host.Tool("verify_figures", token);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, missing.StatusCode);
        await host.Reset();
        var stale = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 1001" }, "facts-here");
        Assert.Equal("rejected", stale["facts"]!["status"]!.ToString());
    }

    [Fact]
    public async Task G1L_has_six_calls_per_person_health_is_free_and_configuration_refresh_clears_buckets()
    {
        await host.Reset("G1L");
        var token = await host.Token();
        for (var call = 1; call <= 8; call++)
        {
            using var response = await host.Tool("book_rank", token);
            Assert.Equal(call <= 6 ? HttpStatusCode.OK : HttpStatusCode.TooManyRequests, response.StatusCode);
            if (call > 6) { Assert.NotNull(response.Headers.RetryAfter); }
        }
        using (var other = await host.Tool("book_rank", await host.Token(GatewayFixture.Writer))) { Assert.Equal(HttpStatusCode.OK, other.StatusCode); }
        using (var health = await host.Client.GetAsync("/channel/health")) { Assert.Equal(HttpStatusCode.OK, health.StatusCode); }
        using (var environment = await host.Client.PostAsJsonAsync("/__contract__/env",
            new { set = new Dictionary<string, string> { ["CHANNEL_RATE_LIMIT_PER_MINUTE"] = "1000", ["AUTH_MODE"] = "none" }, unset = Array.Empty<string>() }))
        { environment.EnsureSuccessStatusCode(); }
        using (var refreshed = await host.Tool("book_rank", token)) { Assert.Equal(HttpStatusCode.OK, refreshed.StatusCode); }
        await host.Reset("G1L");
        using var reset = await host.Tool("book_rank", token);
        Assert.Equal(HttpStatusCode.OK, reset.StatusCode);
    }
}
