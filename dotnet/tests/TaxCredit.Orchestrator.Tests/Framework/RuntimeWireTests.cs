using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Azure.Core;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using TaxCredit.Orchestrator.Hosting;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class RuntimeWireTests
{
    [Fact]
    public async Task Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit()
    {
        using var model = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is 9999."));
        var gateway = new FakeGateway();
        using var transport = new LocalGatewayTransport(gateway);
        using var http = new HttpClient(transport);
        var credential = new LocalCredential();
        using var runtime = new OrchestratorRuntime(Settings(), credential, NullLoggerFactory.Instance, http,
            new Dictionary<string, IChatClient> { ["foundry"] = model });
        await using var app = ResponsesHosting.Build([], runtime.Host, builder => builder.WebApplicationBuilder.WebHost.UseTestServer());
        await app.StartAsync();
        using var client = app.GetTestClient();
        client.DefaultRequestHeaders.Add("x-ms-original-subject-oid", Rig.Oid);
        client.DefaultRequestHeaders.Add("x-ms-original-subject-tid", Rig.Tenant);
        client.DefaultRequestHeaders.Add("x-ms-original-subject-idtype", "user");
        client.DefaultRequestHeaders.Add("x-client-conversation-id", "explicit-conversation");
        using var ready = await client.GetAsync("/readiness");
        Assert.Equal(HttpStatusCode.OK, ready.StatusCode);
        using var response = await client.PostAsJsonAsync("/responses", new
        {
            input = new[] { new { role = "user", content = new[] { new { type = "input_text", text = "How has Cascade trended?" } } } },
            conversation = "conv_00000000000000000000000000000000",
            stream = false,
            store = false,
        });
        var json = JsonNode.Parse(await response.Content.ReadAsStringAsync())!;
        Assert.True(response.IsSuccessStatusCode, json.ToJsonString());
        Assert.Equal("completed", json["status"]!.ToString());
        var text = json["output"]![0]!["content"]![0]!["text"]!.ToString();
        Assert.Contains("494.25", text, StringComparison.Ordinal);
        Assert.DoesNotContain("9999", text, StringComparison.Ordinal);
        Assert.Contains("commentary was withheld", text, StringComparison.Ordinal);
        Assert.Equal(["client_resolve", "client_trend"], gateway.Calls.Select(call => call.Tool));
        Assert.All(gateway.Calls, call =>
        {
            Assert.Equal(Rig.Oid, call.Identity.Oid);
            Assert.Equal("conv_00000000000000000000000000000000", call.Identity.ConversationId);
        });
        Assert.All(transport.Headers, headers => Assert.False(headers.ContainsKey("x-tcc-acting-user")));
        Assert.Equal("rejected", Assert.Single(gateway.Narrations)["guard_status"]!.ToString());
        Assert.Equal(["api://synthetic-gateway/.default"], credential.Scopes);
        await app.StopAsync();
    }

    [Fact]
    public async Task Anonymous_and_debug_off_wire_requests_never_touch_gateway_or_model()
    {
        using var model = new ScriptedModel(ScriptedModel.Error());
        var gateway = new FakeGateway();
        using var transport = new LocalGatewayTransport(gateway);
        using var http = new HttpClient(transport);
        var credential = new LocalCredential();
        using var runtime = new OrchestratorRuntime(Settings(), credential, NullLoggerFactory.Instance, http,
            new Dictionary<string, IChatClient> { ["foundry"] = model });
        await using var app = ResponsesHosting.Build([], runtime.Host, builder => builder.WebApplicationBuilder.WebHost.UseTestServer());
        await app.StartAsync();
        using var client = app.GetTestClient();
        foreach (var question in new[] { "Who should we call first?", "/whoami", "/netcheck", "/modelprobe" })
        {
            using var response = await client.PostAsJsonAsync("/responses", new { input = question, stream = false, store = false });
            Assert.True(response.IsSuccessStatusCode);
        }
        Assert.Empty(transport.Bodies);
        Assert.Empty(model.Seen);
        Assert.Empty(credential.Scopes);
        await app.StopAsync();
    }

    [Theory]
    [InlineData("CHANNEL_MAX_TOOL_CALLS", "0")]
    [InlineData("CHANNEL_TURN_TIMEOUT_SECONDS", "601")]
    [InlineData("AI_PROVIDER_CHAIN", "unregistered")]
    [InlineData("AI_TOTAL_DEADLINE_SECONDS", "NaN")]
    [InlineData("AI_INJECTION_GUARD", "off")]
    [InlineData("AI_OUTPUT_POLICY", "off")]
    public void Invalid_runtime_settings_fail_before_credentials_or_transports(string name, string value)
    {
        var config = Values();
        config[name] = value;
        Assert.Throws<InvalidOperationException>(() => new RuntimeSettings(new ConfigurationBuilder().AddInMemoryCollection(config).Build()));
    }

    [Fact]
    public void Selected_but_unconfigured_foundry_is_not_silently_replaced()
    {
        var settings = Settings();
        Assert.Throws<InvalidOperationException>(() => new ProviderClients(settings, new LocalCredential()));
    }

    internal static RuntimeSettings Settings() => new(new ConfigurationBuilder().AddInMemoryCollection(Values()).Build());
    internal static Dictionary<string, string?> Values() => new(StringComparer.Ordinal)
    {
        ["TENANT_ID"] = Rig.Tenant,
        ["CHANNEL_GATEWAY_URL"] = "https://gateway.example.test",
        ["CHANNEL_GATEWAY_AUDIENCE"] = "api://synthetic-gateway",
        ["AI_PROVIDER_CHAIN"] = "foundry",
        ["AI_RETRY_MAX_ATTEMPTS"] = "1",
    };

    private sealed class LocalCredential : TokenCredential
    {
        internal string[] Scopes { get; private set; } = [];
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            Scopes = requestContext.Scopes;
            return new AccessToken("synthetic-service-auth", DateTimeOffset.UtcNow.AddMinutes(10));
        }
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }
}
