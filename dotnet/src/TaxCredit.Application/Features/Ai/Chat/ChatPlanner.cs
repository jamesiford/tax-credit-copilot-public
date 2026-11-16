using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>Provider failure or an invented tool name never makes routing unavailable.</summary>
public sealed class ChatPlanner(IAiNarrator narrator, IApiPrincipalAccessor principals, IAiTelemetry telemetry)
{
    /// <summary>The selected scope and fenced history help resolve language, not calculate figures.</summary>
    public async ValueTask<IReadOnlyList<string>> PlanAsync(ChatQuery query, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (!narrator.Available(["OrchestratorAgent"])) { return ChatRouting.KeywordIntents(query.Message); }
        var trusted = JsonSerializer.SerializeToElement(new { capabilities = ChatRouting.Intents });
        var history = string.Join("\n", (query.History ?? []).TakeLast(6).Select(turn =>
            $"{(turn.Role == "assistant" ? "copilot" : turn.Role)}: {turn.Text}"));
        var scope = JsonSerializer.Serialize(new { client_id = query.ClientId, tax_year = query.TaxYear, state = query.State });
        var prompt = "Route this question to one or more capabilities.\n\nCAPABILITIES:\n"
            + trusted.GetRawText() + "\n\nCONVERSATION SO FAR:\n<untrusted-conversation>\n" + history
            + "\n</untrusted-conversation>\n\nSELECTED SCOPE: " + scope
            + "\n\nQUESTION:\n<untrusted-question>\n" + query.Message
            + "\n</untrusted-question>\nReply with JSON ONLY: {\"intents\": [\"name\", ...]}. Use the exact names above.";
        var text = new StringBuilder();
        await using var events = ModelStream.Open(() => narrator.StreamAsync("OrchestratorAgent", prompt,
            principals.Current?.Actor ?? "anonymous", trusted, cancellationToken), telemetry, cancellationToken);
        if (events is null) { return ChatRouting.KeywordIntents(query.Message); }
        while (true)
        {
            var next = await ModelStream.MoveAsync(events, telemetry, cancellationToken).ConfigureAwait(false);
            if (next.Failed) { return ChatRouting.KeywordIntents(query.Message); }
            if (!next.HasValue) { break; }
            if (events.Current is TextDelta delta) { text.Append(delta.Text); }
        }
        var raw = text.ToString();
        var start = raw.IndexOf('{');
        var end = raw.LastIndexOf('}');
        try
        {
            return ChatRouting.ValidatePlan(JsonNode.Parse(start >= 0 && end > start ? raw[start..(end + 1)] : JsonSerializer.Serialize(raw)), query.Message);
        }
        catch (JsonException)
        {
            telemetry.Count("ai.routing_invalid_plan");
            return ChatRouting.KeywordIntents(query.Message);
        }
    }
}
