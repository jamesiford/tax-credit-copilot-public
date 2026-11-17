using System.Text.Json;
using System.Text.Json.Nodes;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Execution;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Mcp;

internal sealed record McpCall(HttpContext Http, ChannelCaller Caller);

internal sealed class McpSession : IAsyncDisposable
{
    private readonly ChannelTransport _transport;
    private readonly McpServer _server;
    private readonly Task _running;
    private readonly CancellationTokenSource _stop = new();
    private readonly SemaphoreSlim _gate = new(1, 1);
    internal string Id { get; }
    internal string Owner { get; }
    internal long Stamp { get; }

    internal McpSession(string id, ChannelCaller caller, long stamp, string version, ChannelCatalog catalog, ILoggerFactory logger)
    {
        Id = id; Owner = caller.Acting.TenantId + ":" + caller.Acting.Oid; Stamp = stamp;
        _transport = new(id);
        _server = McpServer.Create(_transport, new McpServerOptions
        {
            ServerInfo = new() { Name = "tcc-channel-gateway", Version = "0.1.0" },
            ServerInstructions = "Every figure these tools return is the platform's own. Quote figures exactly as written.",
            ProtocolVersion = version,
            Capabilities = new() { Tools = new() { ListChanged = false } },
            ScopeRequests = false,
            Handlers = new()
            {
                ListToolsHandler = (_, _) => ValueTask.FromResult(new ListToolsResult { Tools = catalog.McpTools() }),
                CallToolHandler = async (request, _) =>
                {
                    var call = (McpCall)request.JsonRpcRequest.Context!.Items!["channel-call"]!;
                    var parameters = request.Params!;
                    var args = parameters.Arguments is null ? new JsonObject() : JsonSerializer.SerializeToNode(parameters.Arguments)!.AsObject();
                    var outcome = await call.Http.RequestServices.GetRequiredService<ToolPipeline>().RunAsync(
                        call.Caller, parameters.Name, args, null, null, call.Http.Request).ConfigureAwait(false);
                    return new CallToolResult
                    {
                        Content = [new TextContentBlock { Text = ChannelRender.Text(outcome, call.Http.Request) }],
                        StructuredContent = JsonSerializer.SerializeToElement(outcome.Body),
                        IsError = outcome.Status != 200,
                    };
                },
            },
        }, logger);
        _running = _server.RunAsync(_stop.Token);
    }

    internal async Task<JsonObject> ExchangeAsync(JsonObject message, McpCall call, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var rpc = JsonSerializer.Deserialize<JsonRpcMessage>(message.ToJsonString(), McpJsonUtilities.DefaultOptions)!;
            rpc.Context = new() { ExecutionContext = ExecutionContext.Capture(), Items = new Dictionary<string, object?> { ["channel-call"] = call } };
            await _transport.ReceiveAsync(rpc, ct).ConfigureAwait(false);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(35));
            while (true)
            {
                var reply = await _transport.ReplyAsync(timeout.Token).ConfigureAwait(false);
                var body = JsonNode.Parse(JsonSerializer.Serialize(reply, McpJsonUtilities.DefaultOptions))!.AsObject();
                // SDK notifications and a late response to an abandoned HTTP request are not this call's reply.
                if (!body.ContainsKey("method") && JsonNode.DeepEquals(body["id"], message["id"])) { return body; }
            }
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        { throw new ChannelFailure(504, "timeout", "The MCP call timed out; an accepted commit may still land. Retry with the same key.", true); }
        finally { _gate.Release(); }
    }

    internal ValueTask NotifyAsync(JsonObject message, CancellationToken ct) => _transport.ReceiveAsync(
        JsonSerializer.Deserialize<JsonRpcMessage>(message.ToJsonString(), McpJsonUtilities.DefaultOptions)!, ct);

    public async ValueTask DisposeAsync()
    {
        await _stop.CancelAsync().ConfigureAwait(false);
        await _server.DisposeAsync().ConfigureAwait(false);
        try { await _running.ConfigureAwait(false); }
        catch (OperationCanceledException) { }
        _stop.Dispose();
        _gate.Dispose();
    }
}

internal sealed class McpSessions(ChannelCatalog catalog, TimeProvider clock, IIdSource ids, ILoggerFactory logger) : IAsyncDisposable
{
    private readonly Dictionary<string, McpSession> _sessions = new(StringComparer.Ordinal);
    private readonly object _gate = new();

    internal async Task<McpSession> OpenAsync(ChannelCaller caller, string version)
    {
        List<McpSession> expired;
        McpSession session;
        lock (_gate)
        {
            expired = _sessions.Values.Where(s => clock.GetElapsedTime(s.Stamp) >= TimeSpan.FromHours(8)).ToList();
            if (_sessions.Count - expired.Count >= 5000) { expired.Add(_sessions.Values.MinBy(s => s.Stamp)!); }
            foreach (var old in expired) { _sessions.Remove(old.Id); }
            session = new(ids.NewId().ToString("N"), caller, clock.GetTimestamp(), version, catalog, logger);
            _sessions.Add(session.Id, session);
        }
        foreach (var old in expired) { await old.DisposeAsync().ConfigureAwait(false); }
        return session;
    }

    internal McpSession? Find(string? id, ChannelCaller caller)
    {
        lock (_gate)
        {
            return id is not null && _sessions.TryGetValue(id, out var session) &&
                session.Owner == caller.Acting.TenantId + ":" + caller.Acting.Oid &&
                clock.GetElapsedTime(session.Stamp) < TimeSpan.FromHours(8) ? session : null;
        }
    }

    internal async Task<bool> DeleteAsync(string? id, ChannelCaller caller)
    {
        McpSession? session;
        lock (_gate) { session = Find(id, caller); if (session is not null) { _sessions.Remove(session.Id); } }
        if (session is null) { return false; }
        await session.DisposeAsync().ConfigureAwait(false);
        return true;
    }
    internal async ValueTask ResetAsync()
    {
        McpSession[] held;
        lock (_gate) { held = _sessions.Values.ToArray(); _sessions.Clear(); }
        foreach (var session in held) { await session.DisposeAsync().ConfigureAwait(false); }
    }
    public ValueTask DisposeAsync() => ResetAsync();
}
