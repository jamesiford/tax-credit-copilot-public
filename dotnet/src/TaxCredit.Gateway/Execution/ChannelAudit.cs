using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Execution;

internal sealed record AuditHandle(string Id, ChannelCaller Caller, string Tool, string Kind, JsonObject Args, long Stamp);

internal sealed class ChannelAudit(IChannelAuditRepository repository, IIdSource ids, TimeProvider clock, ILogger<ChannelAudit> logger)
{
    private static readonly Action<ILogger, Exception?> ClosingFailed = LoggerMessage.Define(LogLevel.Error,
        new EventId(21, "ChannelAuditUnavailable"), "The channel audit closing event could not be recorded.");

    internal AuditHandle Begin(ChannelCaller caller, string tool, string kind, JsonObject args)
    {
        var handle = Create(caller, tool, kind, args);
        try { Append(handle, 1, "begin", "pending"); }
#pragma warning disable CA1031 // An unavailable durable opening audit must prevent dispatch, without exposing adapter diagnostics.
        catch (Exception) { throw new ChannelFailure(503, "audit_unavailable", "The audit trail is unavailable; nothing was done.", true); }
#pragma warning restore CA1031
        return handle;
    }
    internal AuditHandle Create(ChannelCaller caller, string tool, string kind, JsonObject args) =>
        new(ids.NewId().ToString("N"), caller, tool, kind, args, clock.GetTimestamp());

    internal void Finish(AuditHandle handle, string outcome, string? code = null, JsonObject? result = null)
    {
        try { Append(handle, 2, "end", outcome, code, result); }
#pragma warning disable CA1031 // The durable begin survives; alert rather than masking the accepted business outcome.
        catch (Exception) { ClosingFailed(logger, null); }
#pragma warning restore CA1031
    }

    internal string Single(ChannelCaller caller, string tool, string kind, JsonObject args, string outcome,
        string? code = null, string guard = "n/a")
    {
        var handle = Create(caller, tool, kind, args);
        Append(handle, 1, "single", outcome, code, guard: guard);
        return handle.Id;
    }

    internal void Refusal(ChannelCaller caller, string tool, string kind, JsonObject args, string code)
    {
        try { Single(caller, tool, kind, args, "refused", code); }
#pragma warning disable CA1031 // Refusals stand even when their audit sink is unavailable, with an explicit safe alert.
        catch (Exception) { ClosingFailed(logger, null); }
#pragma warning restore CA1031
    }

    private void Append(AuditHandle handle, int sequence, string phase, string outcome, string? code = null,
        JsonObject? result = null, string guard = "n/a")
    {
        var acting = handle.Caller.Acting;
        repository.Append(new ChannelAuditEvent(new Dictionary<string, object?>
        {
            ["audit_id"] = handle.Id,
            ["event_seq"] = sequence,
            ["phase"] = phase,
            ["correlation_id"] = acting.CorrelationId,
            ["occurred_at"] = Instant(clock.GetUtcNow()),
            ["elapsed_ms"] = phase == "begin" ? null : (long)clock.GetElapsedTime(handle.Stamp).TotalMilliseconds,
            ["channel"] = acting.Channel,
            ["user_oid"] = acting.Oid,
            ["tenant_id"] = acting.TenantId,
            ["user_display_name"] = acting.Name,
            ["user_upn"] = acting.Upn,
            ["identity_assurance"] = acting.Assurance,
            ["conversation_id"] = acting.ConversationId,
            ["tool_name"] = handle.Tool,
            ["action_kind"] = handle.Kind,
            ["client_id"] = Integer(handle.Args, "client_id"),
            ["tax_year"] = Integer(handle.Args, "tax_year"),
            ["request_summary"] = phase == "end" ? null : "Channel call; arguments withheld",
            ["request_sha256"] = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(handle.Args.ToJsonString()))),
            ["outcome"] = outcome,
            ["error"] = code,
            ["run_id"] = result?["provenance"]?["run_id"]?.GetValue<string>(),
            ["trail_sha256"] = result?["provenance"]?["trail_sha256"]?.GetValue<string>(),
            ["numeric_guard"] = handle.Tool == "verify_figures" ? result?["facts"]?["status"]?.GetValue<string>() ?? guard : guard,
            ["is_deterministic_path"] = guard != "rejected",
        }));
    }

    private static long? Integer(JsonObject args, string key) =>
        (args["arguments"] as JsonObject ?? args)[key] is JsonValue value && value.TryGetValue<long>(out var number) ? number : null;
    internal static PyDateTime Instant(DateTimeOffset now) => new(DateOnly.FromDateTime(now.UtcDateTime),
        now.Hour, now.Minute, now.Second, (int)(now.Ticks % TimeSpan.TicksPerSecond / 10), 0);
}
