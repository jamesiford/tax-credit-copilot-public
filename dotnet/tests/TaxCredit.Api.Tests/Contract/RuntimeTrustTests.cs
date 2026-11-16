using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Api.Tests.Contract;

public sealed class RuntimeTrustTests
{
    [Fact]
    public async Task Signed_reads_observe_seeded_stores_and_the_principal_survives_await_without_leaking()
    {
        await using var host = await RuntimeRequests.Start();
        await RuntimeRequests.Reset(host);
        var reader = await RuntimeRequests.Mint(host, new { });
        var writer = await RuntimeRequests.Mint(host, new { oid = RuntimeRequests.Writer });
        using var observed = await RuntimeRequests.Send(host, reader);
        Assert.Equal(200, (int)observed.StatusCode);
        var body = await observed.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(body.GetProperty("manifests").GetInt64() > 0);
        Assert.True(body.GetProperty("rows").GetInt64() > 0);
        Assert.Equal(RuntimeRequests.Reader, body.GetProperty("principal").GetString());
        var calls = Enumerable.Range(0, 8).Select(async n =>
        {
            using var response = await RuntimeRequests.Send(host, n % 2 == 0 ? reader : writer, "/api/me");
            Assert.Equal(200, (int)response.StatusCode);
            Assert.Equal(n % 2 == 0 ? RuntimeRequests.Reader : RuntimeRequests.Writer,
                (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("oid").GetString());
        });
        await Task.WhenAll(calls);
        Assert.Null(host.App.Services.GetRequiredService<IApiPrincipalAccessor>().Current);
        using var anonymous = await host.Client.GetAsync("/api/me");
        Assert.Equal(401, (int)anonymous.StatusCode);
    }

    [Theory]
    [InlineData("""{"key":"other"}""")]
    [InlineData("""{"tid":"00000000-0000-0000-0000-0000000000ff"}""")]
    [InlineData("""{"aud":"not-the-api"}""")]
    [InlineData("""{"iss":"https://invalid.example.test/v2.0"}""")]
    [InlineData("""{"exp_in":-600}""")]
    [InlineData("""{"nbf_in":600}""")]
    public async Task Invalid_rs256_claims_never_reach_a_store_but_public_probes_bypass_them(string specification)
    {
        await using var host = await RuntimeRequests.Start();
        var token = await RuntimeRequests.Mint(host, JsonSerializer.Deserialize<JsonElement>(specification));
        using var response = await RuntimeRequests.Send(host, token);
        Assert.Equal(401, (int)response.StatusCode);
        Assert.NotEmpty(response.Headers.WwwAuthenticate);
        Assert.True((await response.Content.ReadFromJsonAsync<JsonElement>()).TryGetProperty("detail", out _));
        using var health = await RuntimeRequests.Send(host, token, "/api/health");
        Assert.Equal(200, (int)health.StatusCode);
    }

    [Fact]
    public async Task Agent_shape_acting_precedence_original_client_rights_and_delegated_non_elevation_are_real()
    {
        await using var host = await RuntimeRequests.Start();
        var agent = await RuntimeRequests.Mint(host, new { kind = "agent" });
        using var missing = await RuntimeRequests.Send(host, agent, "/api/me");
        Assert.Equal(400, (int)missing.StatusCode);
        using var valid = await RuntimeRequests.Send(host, agent, "/api/me", acting: RuntimeRequests.Acting());
        Assert.Equal(200, (int)valid.StatusCode);
        using var malformed = await RuntimeRequests.Send(host, agent, "/api/claims/assess", HttpMethod.Post, new { }, "not-base64");
        Assert.Equal(400, (int)malformed.StatusCode);
        Assert.Contains("acting", await malformed.Content.ReadAsStringAsync(), StringComparison.OrdinalIgnoreCase);
        using var forbidden = await RuntimeRequests.Send(host, agent, "/api/claims/assess", HttpMethod.Post, new { }, RuntimeRequests.Acting());
        Assert.Equal(403, (int)forbidden.StatusCode);
        Assert.Contains("agent", await forbidden.Content.ReadAsStringAsync(), StringComparison.OrdinalIgnoreCase);
        var restricted = await RuntimeRequests.Mint(host, new { kind = "agent", oid = "00000000-0000-0000-0000-0000000000a3" });
        using var denied = await RuntimeRequests.Send(host, restricted, acting: RuntimeRequests.Acting());
        Assert.Equal(403, (int)denied.StatusCode);
        var mixed = await RuntimeRequests.Mint(host, new { roles = new[] { "TCC.User", "TCC.Agent" } });
        using var mixedRead = await RuntimeRequests.Send(host, mixed, "/api/me");
        Assert.Equal(403, (int)mixedRead.StatusCode);
        var reader = await RuntimeRequests.Mint(host, new { });
        using var unknown = await RuntimeRequests.Send(host, reader, "/api/v2/run-batches/unknown");
        Assert.Equal(404, (int)unknown.StatusCode);
    }
}
