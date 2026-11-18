using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayFixture : IAsyncLifetime
{
    private readonly Action<IServiceCollection>? _configure;
    public GatewayFixture() { }
    internal GatewayFixture(Action<IServiceCollection> configure) => _configure = configure;
    private WebApplication? _app;
    private readonly string _directory = Path.Combine(AppContext.BaseDirectory, "tcc-gateway-test-" + Guid.NewGuid().ToString("N"));
    public HttpClient Client { get; private set; } = null!;
    public IServiceProvider Services => _app!.Services;
    public const string Reader = "00000000-0000-0000-0000-0000000000a1";
    public const string Writer = "00000000-0000-0000-0000-0000000000a2";
    public const string Tenant = "00000000-0000-0000-0000-0000000000aa";

    public async Task InitializeAsync()
    {
        Directory.CreateDirectory(_directory);
        _app = GatewayHost.Build(
        [
            "--urls=http://127.0.0.1:0", "--CONTRACT_HOOKS=1",
            "--OPERATIONAL_DB=" + Path.Combine(_directory, "operations.db"),
            "--ARTIFACT_LOCAL_ROOT=" + Path.Combine(_directory, "bytes"),
        ], builder => builder.Logging.ClearProviders(), _configure);
        await _app.StartAsync();
        var address = _app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
        Client = new HttpClient { BaseAddress = new Uri(address), Timeout = TimeSpan.FromSeconds(45) };
        await Reset();
    }

    public async Task Reset(string profile = "G1")
    {
        using var response = await Client.PostAsJsonAsync("/__contract__/reset", new { profile });
        response.EnsureSuccessStatusCode();
    }
    public async Task<string> Token(string oid = Reader, bool agent = false, JsonObject? overrides = null)
    {
        var specification = new JsonObject
        {
            ["kind"] = agent ? "agent" : "user",
            ["oid"] = oid,
            ["aud"] = "api://contract-gateway",
            ["scp"] = agent ? "" : "Channel.Access",
            ["roles"] = agent ? new JsonArray("Channel.Invoke") : new JsonArray(),
        };
        foreach (var pair in overrides ?? []) { specification[pair.Key] = pair.Value?.DeepClone(); }
        using var reply = await Client.PostAsJsonAsync("/__contract__/mint", specification);
        reply.EnsureSuccessStatusCode();
        return (await reply.Content.ReadFromJsonAsync<JsonObject>())!["token"]!.GetValue<string>();
    }
    public async Task<HttpResponseMessage> Send(string method, string path, string? token = null, object? body = null,
        IReadOnlyDictionary<string, string>? headers = null)
    {
        using var request = new HttpRequestMessage(new HttpMethod(method), path);
        if (token is not null) { request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token); }
        foreach (var pair in headers ?? new Dictionary<string, string>()) { request.Headers.TryAddWithoutValidation(pair.Key, pair.Value); }
        if (body is not null) { request.Content = JsonContent.Create(body); }
        return await Client.SendAsync(request);
    }
    public Task<HttpResponseMessage> Tool(string name, string token, JsonObject? args = null, string conversation = "test-conversation") =>
        Send("POST", "/channel/v1/tools/" + name, token, new { args = args ?? [] },
            new Dictionary<string, string> { ["X-Conversation-Id"] = conversation });
    public async Task<JsonObject> Invoke(string name, string token, JsonObject? args = null, string conversation = "test-conversation")
    {
        using var response = await Tool(name, token, args, conversation);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<JsonObject>())!;
    }
    public async Task<(string Session, JsonObject Body)> Initialize(string token, string version = "2025-11-25")
    {
        using var reply = await Send("POST", "/mcp", token,
            new { jsonrpc = "2.0", id = 1, method = "initialize", @params = new { protocolVersion = version, capabilities = new { }, clientInfo = new { name = "test", version = "1" } } });
        Assert.Equal(HttpStatusCode.OK, reply.StatusCode);
        return (reply.Headers.GetValues("Mcp-Session-Id").Single(), (await reply.Content.ReadFromJsonAsync<JsonObject>())!);
    }
    public Task<HttpResponseMessage> Rpc(string token, string? session, object body) => Send("POST", "/mcp", token, body,
        session is null ? null : new Dictionary<string, string> { ["Mcp-Session-Id"] = session });

    public async Task DisposeAsync()
    {
        Client?.Dispose();
        if (_app is not null) { await _app.DisposeAsync(); }
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
        if (Directory.Exists(_directory)) { Directory.Delete(_directory, true); }
    }
}
