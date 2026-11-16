using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Execution;

internal sealed class NarrationAudit(ChannelAudit audit, IChannelAuditRepository repository, IIdSource ids, TimeProvider clock,
    ILogger<NarrationAudit> logger)
{
    private static readonly Action<ILogger, Exception?> AgentFailed = LoggerMessage.Define(LogLevel.Error,
        new EventId(22, "AgentAuditUnavailable"), "The narration agent audit could not be recorded.");

    internal JsonObject Record(ChannelCaller caller, JsonObject report)
    {
        var schema = JsonNode.Parse("""
            {"type":"object","additionalProperties":false,"required":["agent_name","prompt_sha256","guard_status"],
             "properties":{"agent_name":{"type":"string","minLength":1,"maxLength":100},
             "agent_version":{"type":"string","maxLength":50},"model":{"type":"string","maxLength":100},
             "prompt_sha256":{"type":"string"},"tool_names":{"type":"array","maxItems":20,"items":{"type":"string"}},
             "guard_status":{"type":"string","enum":["pass","rejected"]},"violations_count":{"type":"integer","minimum":0,"maximum":10000},
             "output_summary":{"type":"string","maxLength":400},"conversation_id":{"type":["string","null"],"maxLength":100}}}
            """)!.AsObject();
        try { Application.Features.Ai.Capabilities.CapabilitySchema.Validate(schema, report); }
        catch (Application.Features.Ai.Capabilities.CapabilityException)
        { throw new ChannelFailure(422, "invalid_request", "The body is not a narration report."); }
        var guard = report["guard_status"]!.GetValue<string>();
        var count = report["violations_count"]?.GetValue<int>() ?? 0;
        if (!Regex.IsMatch(report["prompt_sha256"]!.GetValue<string>(), @"\A[0-9a-f]{64}\z", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1)) ||
            guard == "pass" && count != 0)
        { throw new ChannelFailure(422, "invalid_request", "Invalid narration hash or guard verdict."); }
        string id;
        try { id = audit.Single(caller, "narration", "narrate", report, guard == "pass" ? "ok" : "rejected_by_guard", guard: guard); }
#pragma warning disable CA1031 // A required audit failure is explicit; nothing is falsely acknowledged as filed.
        catch (Exception) { throw new ChannelFailure(503, "audit_unavailable", "The audit trail is unavailable.", true); }
#pragma warning restore CA1031
        var recorded = true;
        try
        {
            repository.Append(new AgentActionAudit(new Dictionary<string, object?>
            {
                ["action_id"] = ids.NewId().ToString("N"),
                ["agent_name"] = report["agent_name"]!.GetValue<string>(),
                ["agent_version"] = report["agent_version"]?.GetValue<string>(),
                ["model_deployment"] = report["model"]?.GetValue<string>(),
                ["prompt_hash"] = report["prompt_sha256"]!.GetValue<string>(),
                ["tool_calls"] = (report["tool_names"] ?? new JsonArray()).ToJsonString(),
                ["input_summary"] = "channel narration",
                ["output_summary"] = $"guard={guard}; violations={count}",
                ["user_upn"] = caller.Acting.Actor,
                ["occurred_at"] = ChannelAudit.Instant(clock.GetUtcNow()),
                ["is_deterministic_path"] = guard == "pass",
            }));
        }
#pragma warning disable CA1031 // The channel row is durable; the response and alert explicitly identify the failed companion row.
        catch (Exception) { recorded = false; AgentFailed(logger, null); }
#pragma warning restore CA1031
        return new JsonObject { ["audit_id"] = id, ["agent_action_recorded"] = recorded, ["correlation_id"] = caller.Acting.CorrelationId };
    }
}
