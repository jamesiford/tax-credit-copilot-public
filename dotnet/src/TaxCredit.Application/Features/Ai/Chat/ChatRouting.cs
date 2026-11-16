using System.Text.Json.Nodes;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>Routing only chooses a trusted capability; a model cannot create a new intent.</summary>
public static class ChatRouting
{
    private static readonly (string Intent, string[] Words)[] Keywords =
    [
        ("explain", ["walk me through", "how did you", "how do you", "explain", "show your work", "show the calculation", "show me the calculation"]),
        ("book", ["who should we", "who do we", "who to call", "which client", "which clients", "reach out", "call first", "best client", "next best customer", "next best client", "best customer", "targeting", "who to target", "should we target", "top target", "target list", "across our clients", "across the book", "our book", "top of the list", "prioriti", "worth contacting"]),
        ("at_risk", ["fall off", "fall out", "falling off", "at risk", "drop off", "lose eligibility", "losing eligibility", "close to the threshold", "near the threshold", "barely", "marginal", "fragile", "could we lose", "might we lose", "keep them"]),
        ("trend", ["trend", "since their base year", "since the base year", "base year", "over the years", "year over year", "year-over-year", "history", "subsequent years", "each year", "every year", "prior years"]),
        ("situation", ["situation", "why would i call", "why call", "overview of this client", "client overview", "where do they stand", "what should i say", "brief me", "worth calling", "why are they"]),
        ("simulate", ["what if", "hired", "hire ", "simulate", "what would happen", "next month"]),
        ("multi_state", ["portfolio", "every state", "all our states", "all states", "all jurisdictions", "full credit picture", "complete credit picture", "across our footprint", "full picture", "complete picture", "every credit", "all credits", "entire footprint", "multi-state"]),
        ("discovery", ["other credits", "other credit", "what else", "discover", "may also qualify", "might we qualify", "additional credits"])
    ];

    /// <summary>The exact whitelist shared with deterministic capability selection.</summary>
    public static IReadOnlyDictionary<string, string> Intents { get; } = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["book"] = "who to call ACROSS EVERY CLIENT, ranked by why — the portfolio question. Needs no client selected; naming one would be the opposite of what was asked.",
        ["situation"] = "why this client is worth calling — bands, programmes, years. Claims only.",
        ["eligibility"] = "the credit figure and headcount for the selected client-year.",
        ["at_risk"] = "which employees ALREADY counted toward the credit sit close enough to a statutory floor that they could fall out of it — jobs the client could lose.",
        ["trend"] = "how a client has moved across years, and whether they have been eligible since their base year.",
        ["multi_state"] = "which PROGRAMMES across every state one client may qualify for — a rule-pack scan for the selected client, NOT a view across clients.",
        ["discovery"] = "other programmes the client may qualify for, excluding the one in scope.",
        ["simulate"] = "what-if: hiring, losing, hours or wages against the statutory engine.",
        ["explain"] = "re-narrate the cached calculation trail, step by step."
    };

    /// <summary>The first matching family does not swallow the rest of a compound question.</summary>
    public static IReadOnlyList<string> KeywordIntents(string message)
    {
        ArgumentNullException.ThrowIfNull(message);
        var hits = Keywords.Where(k => k.Words.Any(w => message.Contains(w, StringComparison.OrdinalIgnoreCase))).Select(k => k.Intent).ToArray();
        return hits.Length == 0 ? ["eligibility"] : hits;
    }

    /// <summary>Unknown names are dropped, duplicates collapse, and an unusable plan falls back.</summary>
    public static IReadOnlyList<string> ValidatePlan(JsonNode? raw, string message)
    {
        if (raw is JsonObject obj) { raw = obj["intents"]; }
        IEnumerable<JsonNode?> candidates = raw is JsonArray array ? array : [raw];
        var intents = candidates.Select(n => n?.ToString().Trim().ToLowerInvariant() ?? "")
            .Where(Intents.ContainsKey).Distinct(StringComparer.Ordinal).ToArray();
        return intents.Length == 0 ? KeywordIntents(message) : intents;
    }
}
