using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using ModelContextProtocol.Client;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayProtocolTests(GatewayFixture host) : IClassFixture<GatewayFixture>
{
    [Fact]
    public async Task Ordinary_socket_serves_health_and_not_api_documentation()
    {
        foreach (var path in new[] { "/api/health", "/channel/health", "/channel/ready" })
        { using var response = await host.Client.GetAsync(path); Assert.Equal(HttpStatusCode.OK, response.StatusCode); }
        foreach (var path in new[] { "/docs", "/openapi.json" })
        { using var response = await host.Client.GetAsync(path); Assert.Equal(HttpStatusCode.NotFound, response.StatusCode); }
    }

    [Theory]
    [InlineData("2025-11-25", "2025-11-25")]
    [InlineData("2025-06-18", "2025-06-18")]
    [InlineData("2025-03-26", "2025-03-26")]
    [InlineData("2020-01-01", "2025-11-25")]
    public async Task Official_server_negotiates_supported_versions(string requested, string expected)
    {
        var token = await host.Token();
        var (_, body) = await host.Initialize(token, requested);
        Assert.Equal(expected, body["result"]!["protocolVersion"]!.GetValue<string>());
        Assert.Equal("tcc-channel-gateway", body["result"]!["serverInfo"]!["name"]!.GetValue<string>());
    }

    [Fact]
    public async Task Official_sdk_client_initializes_lists_and_calls_the_real_application()
    {
        var token = await host.Token();
        await using var transport = new HttpClientTransport(new()
        {
            Endpoint = new Uri(host.Client.BaseAddress!, "/mcp"),
            TransportMode = HttpTransportMode.StreamableHttp,
            AdditionalHeaders = new Dictionary<string, string> { ["Authorization"] = "Bearer " + token },
        });
        await using var client = await McpClient.CreateAsync(transport);
        var tools = await client.ListToolsAsync();
        Assert.Equal(36, tools.Count);
        var result = await client.CallToolAsync("client_situation", new Dictionary<string, object?> { ["client_id"] = 1001 });
        Assert.False(result.IsError);
        Assert.Equal("client_situation", result.StructuredContent!.Value.GetProperty("tool").GetString());
    }

    [Fact]
    public async Task Rest_and_mcp_catalogues_and_authorized_facts_are_equal()
    {
        var token = await host.Token();
        var (session, _) = await host.Initialize(token);
        using var listed = await host.Rpc(token, session, new { jsonrpc = "2.0", id = 2, method = "tools/list" });
        var mcp = (await listed.Content.ReadFromJsonAsync<JsonObject>())!["result"]!["tools"]!.AsArray();
        using var rest = await host.Send("GET", "/channel/v1/tools", token);
        var tools = (await rest.Content.ReadFromJsonAsync<JsonObject>())!["tools"]!.AsArray();
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !Directory.Exists(Path.Combine(root.FullName, "contract", "inventory"))) { root = root.Parent; }
        Assert.NotNull(root);
        var inventory = JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(root.FullName, "contract", "inventory", "channel.json")))!["tools"]!.AsArray();
        Assert.Equal(36, mcp.Count);
        Assert.Equal(36, tools.Count);
        foreach (var spec in tools.OfType<JsonObject>())
        {
            var actual = mcp.OfType<JsonObject>().Single(t => t["name"]!.ToString() == spec["name"]!.ToString());
            var pinned = inventory.OfType<JsonObject>().Single(t => t["name"]!.ToString() == spec["name"]!.ToString());
            Assert.True(JsonNode.DeepEquals(spec["schema"], actual["inputSchema"]));
            Assert.True(JsonNode.DeepEquals(pinned["schema"], spec["schema"]));
            Assert.Equal(pinned["description"]!.ToString(), spec["description"]!.ToString());
            Assert.Equal(pinned["channel_description"]!.ToString(), actual["description"]!.ToString());
            Assert.Equal(spec["kind"]!.ToString() == "read", actual["annotations"]!["readOnlyHint"]!.GetValue<bool>());
        }
        Assert.DoesNotContain(tools, item => item!["name"]!.ToString() == "claim_package_redeem");
        var expected = await host.Invoke("client_situation", token, new() { ["client_id"] = 1001 });
        using var call = await host.Rpc(token, session, new { jsonrpc = "2.0", id = 3, method = "tools/call", @params = new { name = "client_situation", arguments = new { client_id = 1001 } } });
        var envelope = (await call.Content.ReadFromJsonAsync<JsonObject>())!["result"]!["structuredContent"]!;
        Assert.True(JsonNode.DeepEquals(expected["facts"], envelope["facts"]));
    }

    [Fact]
    public async Task Debug_configuration_adds_only_the_documented_local_diagnostic()
    {
        using var changed = await host.Client.PostAsJsonAsync("/__contract__/env",
            new { set = new Dictionary<string, string> { ["CHANNEL_DEBUG_WHOAMI"] = "1" }, unset = Array.Empty<string>() });
        changed.EnsureSuccessStatusCode();
        try
        {
            var token = await host.Token();
            using var response = await host.Send("GET", "/channel/v1/tools", token);
            var tools = (await response.Content.ReadFromJsonAsync<JsonObject>())!["tools"]!.AsArray();
            Assert.Equal(37, tools.Count);
            Assert.Single(tools, item => item!["name"]!.ToString() == "channel_ping");
            var diagnostic = await host.Invoke("channel_ping", token);
            Assert.Equal("delegated", diagnostic["facts"]!["caller_shape"]!.ToString());
        }
        finally { await host.Reset(); }
    }

    [Fact]
    public async Task Session_lifecycle_is_person_bound_and_reset_invalidates_it()
    {
        var token = await host.Token();
        var other = await host.Token(GatewayFixture.Writer);
        var (session, _) = await host.Initialize(token);
        var body = new { jsonrpc = "2.0", id = 2, method = "tools/list" };
        using (var absent = await host.Rpc(token, null, body)) { Assert.Equal(HttpStatusCode.BadRequest, absent.StatusCode); }
        using (var missing = await host.Rpc(token, "unknown", body)) { Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode); }
        using (var wrong = await host.Rpc(other, session, body)) { Assert.Equal(HttpStatusCode.NotFound, wrong.StatusCode); }
        var headers = new Dictionary<string, string> { ["Mcp-Session-Id"] = session };
        using (var wrong = await host.Send("DELETE", "/mcp", other, headers: headers)) { Assert.Equal(HttpStatusCode.NotFound, wrong.StatusCode); }
        using (var own = await host.Rpc(token, session, body)) { Assert.Equal(HttpStatusCode.OK, own.StatusCode); }
        using (var deleted = await host.Send("DELETE", "/mcp", token, headers: headers)) { Assert.Equal(HttpStatusCode.OK, deleted.StatusCode); }
        using (var again = await host.Send("DELETE", "/mcp", token, headers: headers)) { Assert.Equal(HttpStatusCode.NotFound, again.StatusCode); }
        using (var after = await host.Rpc(token, session, body)) { Assert.Equal(HttpStatusCode.NotFound, after.StatusCode); }
        var (second, _) = await host.Initialize(token);
        await host.Reset();
        using var reset = await host.Rpc(token, second, body);
        Assert.Equal(HttpStatusCode.NotFound, reset.StatusCode);
    }

    [Theory]
    [InlineData("""{"jsonrpc":"2.0","id":true,"method":"initialize"}""", 400, -32600)]
    [InlineData("""{"jsonrpc":"2.0","id":null,"method":"initialize"}""", 400, -32600)]
    [InlineData("""[]""", 400, -32600)]
    [InlineData("""{""", 400, -32700)]
    [InlineData("", 400, -32700)]
    public async Task Invalid_protocol_bodies_do_not_become_server_errors(string body, int status, int code)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/mcp");
        request.Headers.Authorization = new("Bearer", await host.Token());
        request.Content = new StringContent(body, System.Text.Encoding.UTF8, "application/json");
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(status, (int)response.StatusCode);
        Assert.Equal(code, (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.GetValue<int>());
    }

    [Fact]
    public async Task Origin_precedes_identity_get_needs_no_token_and_notifications_do_not_execute()
    {
        using (var response = await host.Send("POST", "/mcp", body: new { }, headers: new Dictionary<string, string> { ["Origin"] = "https://not-allowed.test" }))
        { Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode); }
        using (var response = await host.Send("GET", "/mcp")) { Assert.Equal(HttpStatusCode.MethodNotAllowed, response.StatusCode); }
        var token = await host.Token();
        using var notification = await host.Rpc(token, null, new { jsonrpc = "2.0", method = "tools/call", @params = new { name = "claim_record_commit" } });
        Assert.Equal(HttpStatusCode.Accepted, notification.StatusCode);
        using var clientResponse = await host.Rpc(token, null, new { jsonrpc = "2.0", id = 3, result = new { ignored = true } });
        Assert.Equal(HttpStatusCode.Accepted, clientResponse.StatusCode);
    }
}
