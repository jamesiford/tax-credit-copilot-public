using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Execution;

internal sealed record ChannelOutcome(int Status, JsonObject Body, int? RetryAfter = null);

internal sealed class ToolPipeline(ChannelCatalog catalog, CapabilityService capabilities, ChannelState state,
    ChannelAudit audit, IApiPrincipalAccessor principals, IWriterEntitlement writers, ILogger<ToolPipeline> logger)
{
    private static readonly Action<ILogger, Exception?> Failed = LoggerMessage.Define(LogLevel.Error,
        new EventId(23, "ToolExecutionFailed"), "The channel tool failed unexpectedly; its closing audit records the failure.");
    private static readonly Action<ILogger, Exception?> WriterFailed = LoggerMessage.Define(LogLevel.Error,
        new EventId(24, "ChannelWriterUnavailable"), "The channel writer entitlement could not be verified; access is refused.");
    internal void RefuseEnvelope(ChannelCaller caller, string name, string code)
    {
        var kind = catalog.Find(name)?["kind"]?.GetValue<string>();
        if (kind is "write_prepare" or "write_commit") { audit.Refusal(caller, name, kind, [], code); }
    }

    internal async Task<ChannelOutcome> RunAsync(ChannelCaller caller, string name, JsonObject args,
        string? idempotencyKey, string? confirmationToken, HttpRequest request)
    {
        var correlation = caller.Acting.CorrelationId ?? "";
        var spec = catalog.Find(name);
        if (spec is null) { return Error(new(404, "unknown_tool", "No such tool."), correlation); }
        var kind = spec["kind"]!.GetValue<string>();
        var limit = state.Spend(caller.Acting.Oid);
        if (!limit.Allowed)
        {
            audit.Refusal(caller, name, kind, args, "rate_limited");
            var body = new ChannelFailure(429, "rate_limited", "Too many calls; slow down.", true).Body(correlation);
            body["error"]!["retry_after_seconds"] = limit.RetryAfterSeconds;
            return new(429, body, limit.RetryAfterSeconds);
        }
        if (kind == "write_commit" && !await IsWriter(caller.Acting.Oid, request.HttpContext.RequestAborted).ConfigureAwait(false))
        {
            audit.Refusal(caller, name, kind, args, "not_authorized");
            return Error(new(403, "not_authorized", "This user is not entitled to make changes."), correlation);
        }
        AuditHandle? handle = null;
        ChannelOutcome outcome;
        try
        {
            if (kind == "read") { handle = audit.Begin(caller, name, kind, args); }
            JsonObject result;
            using (principals.Push(caller.Principal))
            {
                if (name is "verify_figures" or "channel_ping")
                {
                    CapabilitySchema.Validate(spec["schema"]!.AsObject(), args);
                    result = name == "verify_figures" ? state.Verify(caller, args) : Ping(caller, request);
                }
                else
                {
                    result = await capabilities.InvokeAsync(name, args, idempotencyKey, confirmationToken,
                        request.HttpContext.RequestAborted).ConfigureAwait(false);
                }
            }
            if (result["facts"] is not JsonObject facts || result["blocks"] is not JsonArray)
            { throw new ChannelFailure(502, "bad_response", "The application returned an invalid tool result.", true); }
            if (JsonSerializer.SerializeToUtf8Bytes(result).Length > 1024 * 1024)
            { throw new ChannelFailure(502, "bad_response", "The tool result exceeds its delivery limit.", true); }
            var userLane = (result["user_only_facts"] as JsonArray)?.Count > 0 ||
                result["blocks"]!.AsArray().Any(b => b?["audience"] is { } audience && audience.GetValue<string>() != "both");
            if (!caller.Acting.IsFirstParty && userLane &&
                !await IsWriter(caller.Acting.Oid, request.HttpContext.RequestAborted).ConfigureAwait(false))
            { throw new ChannelFailure(403, "employee_level_not_allowed", "Employee-level rows require an entitled first-party channel or a writer."); }
            state.Record(caller, name, facts);
            result["correlation_id"] = correlation;
            outcome = new(200, result);
        }

        catch (CapabilityException error) { outcome = new(error.StatusCode, WithCorrelation(error.Body(), correlation)); }
        catch (ChannelFailure error) { outcome = Error(error, correlation); }
        catch (OperationCanceledException) when (request.HttpContext.RequestAborted.IsCancellationRequested)
        {
            if (handle is not null) { audit.Finish(handle, "error", "cancelled"); }
            throw;
        }
        catch (OperationCanceledException) { outcome = Error(new(504, "timeout", "The operation timed out; an accepted commit may still land. Retry with the same key.", true), correlation); }
        catch (TimeoutException) { outcome = Error(new(504, "timeout", "The call timed out; an accepted commit may still land. Retry with the same key.", true), correlation); }
#pragma warning disable CA1031 // Close the required opening audit and translate the boundary failure without private diagnostics.
        catch (Exception)
        {
            Failed(logger, null);
            outcome = Error(new(500, "internal_error", "The application failed unexpectedly.", true), correlation);
        }
#pragma warning restore CA1031
        if (handle is not null)
        {
            audit.Finish(handle, outcome.Status == 200 ? "ok" : outcome.Status == 403 ? "refused" : "error",
                outcome.Body["error"]?["code"]?.GetValue<string>(), outcome.Body);
        }
        else if (outcome.Status != 200 && outcome.Body["error"]?["code"]?.GetValue<string>() is
            "invalid_arguments" or "unknown_tool" or "not_implemented" or "client_not_authorized" or "timeout" or "bad_response")
        { audit.Refusal(caller, name, kind, args, outcome.Body["error"]!["code"]!.GetValue<string>()); }
        return outcome;
    }

    private async ValueTask<bool> IsWriter(string person, CancellationToken ct)
    {
        try { return await writers.IsWriterAsync(person, ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
#pragma warning disable CA1031 // An unavailable entitlement fails closed, with an explicit safe operational alert.
        catch (Exception) { WriterFailed(logger, null); return false; }
#pragma warning restore CA1031
    }

    private static JsonObject Ping(ChannelCaller caller, HttpRequest request) =>
        new CapabilityResult("channel_ping", new JsonObject
        {
            ["gateway_version"] = "0.1.0",
            ["caller_shape"] = caller.Kind,
            ["authorised_by"] = caller.Via,
            ["acting_user_received"] = new JsonObject(request.Headers.Where(h => h.Key.StartsWith("x-acting-", StringComparison.OrdinalIgnoreCase) ||
                h.Key.Equals("x-channel", StringComparison.OrdinalIgnoreCase) || h.Key.Equals("x-conversation-id", StringComparison.OrdinalIgnoreCase) ||
                h.Key.Equals("x-correlation-id", StringComparison.OrdinalIgnoreCase))
                .Select(h => KeyValuePair.Create(h.Key.ToLowerInvariant(), (JsonNode?)JsonValue.Create(h.Value.ToString())))),
            ["acting_user_resolved"] = new JsonObject
            {
                ["oid"] = caller.Acting.Oid,
                ["tenant_id"] = caller.Acting.TenantId,
                ["channel"] = caller.Acting.Channel,
                ["assurance"] = caller.Acting.Assurance
            },
            ["api_reachable"] = true,
        }).ToJson();
    private static JsonObject WithCorrelation(JsonObject body, string correlation) { body["correlation_id"] = correlation; return body; }
    private static ChannelOutcome Error(ChannelFailure failure, string correlation) => new(failure.Status, failure.Body(correlation));
}
