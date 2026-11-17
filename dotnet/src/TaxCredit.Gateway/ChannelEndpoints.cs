using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Execution;
using TaxCredit.Gateway.Mcp;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway;

internal static class ChannelEndpoints
{
    internal static void Map(WebApplication app)
    {
        app.MapGet("/channel/health", () => Results.Json(new { status = "ok" }));
        app.MapGet("/channel/ready", (IRuntimeConfiguration settings) => Results.Json(new
        { ready = true, store = settings.Get("CHANNEL_STORE") ?? settings.Get("TCC_PERSISTENCE_PROVIDER") ?? "sqlite" }));
        app.MapGet("/channel/v1/tools", async (HttpContext http, ChannelAuthenticator auth, ChannelCatalog catalog) =>
        {
            _ = await auth.AuthenticateAsync(http.Request).ConfigureAwait(false);
            return Json(200, new JsonObject { ["tools"] = catalog.Offered() });
        });
        app.MapPost("/channel/v1/tools/{tool}", RunTool);
        app.MapPost("/channel/v1/audit/narration", async (HttpContext http, ChannelAuthenticator auth, NarrationAudit audit) =>
        {
            var caller = await auth.AuthenticateAsync(http.Request).ConfigureAwait(false);
            if (caller.Kind != "agent") { throw new ChannelFailure(403, "not_authorized", "Only the orchestrator reports narrations."); }
            return Json(200, audit.Record(caller, ParseObject(await ReadBody(http.Request).ConfigureAwait(false), "invalid_request")));
        });
        app.MapGet("/channel/v1/downloads/{ticket}", async (string ticket, HttpContext http, ChannelAuthenticator auth, ChannelDownloads downloads) =>
        {
            var caller = http.Request.Headers.ContainsKey("Authorization") ? await auth.AuthenticateAsync(http.Request).ConfigureAwait(false) : null;
            return await downloads.ServeAsync(ticket, caller, http).ConfigureAwait(false);
        });
        app.MapPost("/mcp", McpEndpoint.Post);
        app.MapGet("/mcp", async (HttpContext http, IRuntimeConfiguration settings) =>
        {
            var refusal = McpEndpoint.RefuseOrigin(http.Request, settings);
            if (refusal is not null) { return refusal; }
            http.Response.Headers.Allow = "POST, DELETE";
            return await EmptyStatus(http, 405).ConfigureAwait(false);
        });
        app.MapDelete("/mcp", async (HttpContext http, IRuntimeConfiguration settings, ChannelAuthenticator auth, McpSessions sessions) =>
        {
            var refusal = McpEndpoint.RefuseOrigin(http.Request, settings);
            if (refusal is not null) { return refusal; }
            var caller = await auth.AuthenticateAsync(http.Request).ConfigureAwait(false);
            return await EmptyStatus(http, await sessions.DeleteAsync(ChannelAuthenticator.Header(http.Request, "Mcp-Session-Id"), caller).ConfigureAwait(false) ? 200 : 404).ConfigureAwait(false);
        });
    }

    private static async Task<IResult> EmptyStatus(HttpContext http, int status)
    {
        http.Response.StatusCode = status;
        await http.Response.StartAsync(http.RequestAborted).ConfigureAwait(false);
        return Results.Empty;
    }

    private static async Task<IResult> RunTool(string tool, HttpContext http, ChannelAuthenticator auth, ToolPipeline pipeline)
    {
        var caller = await auth.AuthenticateAsync(http.Request).ConfigureAwait(false);
        JsonObject? args;
        string? key, token;
        try
        {
            var body = ParseObject(await ReadBody(http.Request).ConfigureAwait(false), "invalid_request");
            args = body["args"] as JsonObject;
            if (body.ContainsKey("args") && args is null) { throw new ChannelFailure(422, "invalid_request", "Args must be an object."); }
            key = OptionalText(body, "idempotency_key", 200);
            token = OptionalText(body, "confirmation_token", 500);
        }
        catch (ChannelFailure failure)
        {
            pipeline.RefuseEnvelope(caller, tool, failure.Code);
            throw;
        }
        var result = await pipeline.RunAsync(caller, tool, args ?? [], key, token, http.Request).ConfigureAwait(false);
        if (result.RetryAfter is { } retry) { http.Response.Headers.RetryAfter = retry.ToString(System.Globalization.CultureInfo.InvariantCulture); }
        return Json(result.Status, result.Body);
    }

    internal static async Task<string> ReadBody(HttpRequest request)
    {
        const int limit = 65536;
        if (request.ContentLength > limit) { throw TooLarge(); }
        using var buffer = new MemoryStream();
        var chunk = new byte[8192];
        int read;
        while ((read = await request.Body.ReadAsync(chunk, request.HttpContext.RequestAborted).ConfigureAwait(false)) != 0)
        {
            if (buffer.Length + read > limit) { throw TooLarge(); }
            buffer.Write(chunk, 0, read);
        }
        return Encoding.UTF8.GetString(buffer.GetBuffer(), 0, (int)buffer.Length);
    }
    private static ChannelFailure TooLarge() => new(413, "request_too_large", "The body exceeds 65536 bytes.");
    internal static JsonObject ParseObject(string raw, string code)
    {
        try { return JsonNode.Parse(raw.Length == 0 ? "{}" : raw) as JsonObject ?? throw new JsonException(); }
        catch (JsonException) { throw new ChannelFailure(422, code, "The body must be a JSON object."); }
    }
    private static string? OptionalText(JsonObject body, string name, int maximum) => body[name] is null ? null :
        body[name] is JsonValue value && value.TryGetValue<string>(out var text) && text.Length <= maximum ? text :
        throw new ChannelFailure(422, "invalid_request", "An envelope field has an invalid type or length.");
    internal static IResult Json(int status, JsonObject body) => Results.Json(body, statusCode: status);
}
