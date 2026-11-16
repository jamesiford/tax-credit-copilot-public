using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayIdentityTests(GatewayFixture host) : IClassFixture<GatewayFixture>
{
    private static Dictionary<string, string> Headers() => new()
    {
        ["X-Acting-User-Oid"] = GatewayFixture.Reader,
        ["X-Acting-User-Name"] = "Synthetic Person",
        ["X-Acting-Tenant"] = GatewayFixture.Tenant,
        ["X-Channel"] = "teams",
        ["X-Conversation-Id"] = "identity-conversation",
        ["X-Correlation-Id"] = "identity-correlation",
    };

    [Theory]
    [InlineData("none", 401, "unauthenticated")]
    [InlineData("garbage", 401, "unauthenticated")]
    [InlineData("expired", 401, "unauthenticated")]
    [InlineData("future", 401, "unauthenticated")]
    [InlineData("forged", 401, "unauthenticated")]
    [InlineData("wrong-audience", 401, "unauthenticated")]
    [InlineData("wrong-issuer", 401, "unauthenticated")]
    [InlineData("no-scope", 403, "missing_scope")]
    [InlineData("mixed", 403, "mixed_token")]
    [InlineData("other-tenant", 403, "tenant_mismatch")]
    [InlineData("no-oid", 403, "tenant_mismatch")]
    [InlineData("bad-claims", 401, "unauthenticated")]
    [InlineData("agent-no-role", 403, "caller_not_allowed")]
    [InlineData("agent-with-scope", 403, "mixed_token")]
    public async Task Token_shapes_are_cryptographically_verified_and_separate(string shape, int status, string code)
    {
        var overrides = shape switch
        {
            "expired" => new JsonObject { ["exp_in"] = -3600 },
            "future" => new JsonObject { ["nbf_in"] = 3600 },
            "forged" => new JsonObject { ["key"] = "other" },
            "wrong-audience" => new JsonObject { ["aud"] = "not-the-channel" },
            "wrong-issuer" => new JsonObject { ["iss"] = "https://not-an-issuer.test" },
            "no-scope" => new JsonObject { ["scp"] = "" },
            "mixed" => new JsonObject { ["roles"] = new JsonArray("Channel.Invoke") },
            "other-tenant" => new JsonObject { ["tid"] = "00000000-0000-0000-0000-0000000000bb" },
            "no-oid" => new JsonObject { ["drop"] = new JsonArray("oid") },
            "bad-claims" => new JsonObject { ["claims"] = new JsonObject { ["roles"] = new JsonArray(1) } },
            "agent-no-role" => new JsonObject { ["roles"] = new JsonArray("Unrelated.Role") },
            "agent-with-scope" => new JsonObject { ["claims"] = new JsonObject { ["scp"] = "Channel.Access" } },
            _ => new JsonObject(),
        };
        var token = shape == "none" ? null : shape == "garbage" ? "invalid-token" :
            await host.Token(agent: shape.StartsWith("agent-", StringComparison.Ordinal), overrides: overrides);
        using var response = await host.Send("GET", "/channel/v1/tools", token, headers: Headers());
        Assert.Equal(status, (int)response.StatusCode);
        var body = (await response.Content.ReadFromJsonAsync<JsonObject>())!;
        Assert.Equal(code, body["error"]!["code"]!.GetValue<string>());
        Assert.NotNull(body["error"]!["retryable"]);
        if (status == 401) { Assert.Equal("Bearer", response.Headers.WwwAuthenticate.Single().Scheme); }
    }

    [Theory]
    [InlineData("X-Acting-Tenant", null, 400, "invalid_acting_user")]
    [InlineData("X-Acting-Tenant", "00000000-0000-0000-0000-0000000000bb", 403, "tenant_mismatch")]
    [InlineData("X-Acting-User-Oid", "invalid", 400, "invalid_acting_user")]
    [InlineData("X-Acting-User-Name", null, 400, "invalid_acting_user")]
    [InlineData("X-Conversation-Id", null, 400, "invalid_acting_user")]
    [InlineData("X-Channel", null, 400, "invalid_acting_user")]
    [InlineData("X-Channel", "cowork", 400, "invalid_acting_user")]
    [InlineData("X-Channel", "unknown", 400, "invalid_acting_user")]
    [InlineData("X-Correlation-Id", "bad space", 400, "invalid_correlation_id")]
    [InlineData("X-Acting-User-Name", "too-long", 400, "invalid_acting_user")]
    public async Task Agent_assertions_require_the_complete_bound_person_context(string header, string? value, int status, string code)
    {
        var headers = Headers();
        if (value is null) { headers.Remove(header); }
        else { headers[header] = value == "too-long" ? new string('a', 257) : value; }
        using var response = await host.Send("GET", "/channel/v1/tools", await host.Token(agent: true), headers: headers);
        Assert.Equal(status, (int)response.StatusCode);
        Assert.Equal(code, (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.GetValue<string>());
    }

    [Fact]
    public async Task Delegated_headers_cannot_impersonate_and_first_party_agent_can_call()
    {
        var headers = Headers();
        headers["X-Acting-User-Oid"] = GatewayFixture.Writer;
        using var refused = await host.Send("POST", "/channel/v1/tools/claim_record_commit", await host.Token(),
            new { args = new { } }, headers);
        Assert.Equal(HttpStatusCode.Forbidden, refused.StatusCode);
        using var agent = await host.Send("POST", "/channel/v1/tools/client_situation", await host.Token(agent: true),
            new { args = new { client_id = 1001 } }, Headers());
        Assert.Equal(HttpStatusCode.OK, agent.StatusCode);
        var (session, _) = await host.Initialize(await host.Token());
        using var initialized = await host.Send("POST", "/mcp", await host.Token(agent: true),
            new { jsonrpc = "2.0", id = 1, method = "initialize" }, Headers());
        Assert.Equal(HttpStatusCode.OK, initialized.StatusCode);
        Assert.False(string.IsNullOrEmpty(session));
    }

    [Fact]
    public async Task Body_and_envelope_bounds_fail_before_dispatch_and_mcp_parsing_precedes_identity()
    {
        var token = await host.Token();
        using var large = await host.Send("POST", "/channel/v1/tools/client_situation", token, new { args = new { text = new string('x', 65536) } });
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, large.StatusCode);
        using var key = await host.Send("POST", "/channel/v1/tools/claim_record_commit", token, new { args = new { }, idempotency_key = new string('x', 201) });
        Assert.Equal(HttpStatusCode.UnprocessableEntity, key.StatusCode);
        using var malformed = await host.Send("POST", "/mcp", body: new[] { 1, 2 });
        Assert.Equal(HttpStatusCode.BadRequest, malformed.StatusCode);
    }

    [Fact]
    public async Task A_delegated_preview_requires_writer_entitlement_even_when_the_portal_makes_it_optional()
    {
        var args = new JsonObject
        {
            ["client_id"] = 1001,
            ["program_code"] = "GA_JTC",
            ["tax_year"] = 2025,
            ["status"] = "proposed",
        };
        using var reader = await host.Tool("claim_record_prepare", await host.Token(), args);
        Assert.Equal(HttpStatusCode.Forbidden, reader.StatusCode);
        using var writer = await host.Tool("claim_record_prepare", await host.Token(GatewayFixture.Writer), args);
        Assert.Equal(HttpStatusCode.OK, writer.StatusCode);
    }
}
