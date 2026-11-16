using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Execution;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Mcp;

internal static class McpEndpoint
{
    internal static readonly string[] Versions = ["2025-11-25", "2025-06-18", "2025-03-26"];

    internal static IResult? RefuseOrigin(HttpRequest request, IRuntimeConfiguration settings)
    {
        if (!request.Headers.TryGetValue("Origin", out var origin)) { return null; }
        var allowed = (settings.Get("CHANNEL_MCP_ALLOWED_ORIGINS") ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        return allowed.Any(value => value.TrimEnd('/').Equals(origin.ToString().Trim().TrimEnd('/'), StringComparison.OrdinalIgnoreCase)) ? null :
            ChannelEndpoints.Json(403, new ChannelFailure(403, "origin_not_allowed", "This Origin is not allowed.").Body());
    }

    internal static async Task<IResult> Post(HttpContext context, ChannelAuthenticator authenticator,
        McpSessions sessions, ChannelCatalog catalog, IRuntimeConfiguration settings, ToolPipeline pipeline)
    {
        var refused = RefuseOrigin(context.Request, settings);
        if (refused is not null) { return refused; }
        var raw = await ChannelEndpoints.ReadBody(context.Request).ConfigureAwait(false);
        JsonObject message;
        try
        {
            if (JsonNode.Parse(raw) is not JsonObject obj || obj["jsonrpc"] is not JsonValue rpc ||
                !rpc.TryGetValue<string>(out var rpcVersion) || rpcVersion != "2.0" ||
                !(obj["method"] is JsonValue method && method.TryGetValue<string>(out _) ||
                    obj.ContainsKey("id") && obj.ContainsKey("result") != obj.ContainsKey("error")))
            { return RpcError(null, -32600, "Expected one JSON-RPC message.", 400); }
            message = obj;
        }
        catch (JsonException) { return RpcError(null, -32700, "The body is not JSON.", 400); }
        var sid = ChannelAuthenticator.Header(context.Request, "Mcp-Session-Id");
        var caller = await authenticator.AuthenticateAsync(context.Request, sid).ConfigureAwait(false);
        var methodName = message["method"]?.GetValue<string>();
        var version = ChannelAuthenticator.Header(context.Request, "MCP-Protocol-Version");
        if (methodName != "initialize" && version is not null && !Versions.Contains(version, StringComparer.Ordinal))
        { return RpcError(null, -32600, "Unsupported MCP-Protocol-Version.", 400); }
        if (methodName is null || !message.ContainsKey("id"))
        {
            if (methodName is not null && sessions.Find(sid, caller) is { } notified)
            { await notified.NotifyAsync(message, context.RequestAborted).ConfigureAwait(false); }
            return Results.StatusCode(202);
        }
        var id = message["id"];
        if (id is not JsonValue idValue || !(idValue.TryGetValue<string>(out _) ||
            idValue.GetValueKind() == JsonValueKind.Number && idValue.TryGetValue<long>(out _)))
        { return RpcError(null, -32600, "A request id must be a string or integer.", 400); }
        if (message["params"] is not null && message["params"] is not JsonObject)
        { return RpcError(id, -32602, "Params must be an object."); }
        message["params"] ??= new JsonObject();
        McpSession? session;
        if (methodName == "initialize")
        {
            var parameters = message["params"]!.AsObject();
            var asked = parameters["protocolVersion"]?.ToString();
            parameters["protocolVersion"] = Versions.Contains(asked, StringComparer.Ordinal) ? asked : Versions[0];
            parameters["capabilities"] ??= new JsonObject();
            parameters["clientInfo"] ??= new JsonObject { ["name"] = "channel-client", ["version"] = "1" };
            session = await sessions.OpenAsync(caller, parameters["protocolVersion"]!.GetValue<string>()).ConfigureAwait(false);
            context.Response.Headers["Mcp-Session-Id"] = session.Id;
        }
        else
        {
            if (sid is null) { return RpcError(id, -32600, "Mcp-Session-Id is required.", 400); }
            session = sessions.Find(sid, caller);
            if (session is null) { return RpcError(id, -32600, "Unknown session; initialize again.", 404); }
            if (methodName == "tools/call")
            {
                var args = message["params"]!.AsObject();
                if (args["name"] is not JsonValue name || !name.TryGetValue<string>(out var tool))
                { return RpcError(id, -32602, "Tools/call requires a name and arguments object."); }
                if (args["arguments"] is not null && args["arguments"] is not JsonObject)
                {
                    pipeline.RefuseEnvelope(caller, tool, "invalid_arguments");
                    return RpcError(id, -32602, "Tools/call requires a name and arguments object.");
                }
                if (catalog.Find(tool) is null) { return RpcError(id, -32602, "Unknown tool."); }
                args["arguments"] ??= new JsonObject();
            }
        }
        var result = await session.ExchangeAsync(message, new(context, caller), context.RequestAborted).ConfigureAwait(false);
        return ChannelEndpoints.Json(200, result);
    }

    internal static IResult RpcError(JsonNode? id, int code, string message, int status = 200) =>
        ChannelEndpoints.Json(status, new JsonObject
        {
            ["jsonrpc"] = "2.0",
            ["id"] = id?.DeepClone(),
            ["error"] = new JsonObject { ["code"] = code, ["message"] = message },
        });
}
