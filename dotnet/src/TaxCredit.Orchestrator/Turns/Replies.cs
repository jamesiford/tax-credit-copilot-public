using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Turns;

/// <summary>The platform's deterministic sentences contain no invented engine figures.</summary>
public static class Replies
{
    /// <summary>Anonymous callers reach neither gateway nor model.</summary>
    public const string Unattributed = "I can't tell who you are in this conversation, so I won't run anything. Every answer and every change here is recorded against a named person.";
    /// <summary>Ordinary fallback capability guidance.</summary>
    public const string Help = "I can answer from the platform's calculations: who to call across the book, one client's situation, eligibility and credit for a tax year, trend since the base year, jobs at risk of falling out, other programmes, what-ifs and the calculation walk-through. Ask about a client by name.";
    /// <summary>Injection refusals occur before model access.</summary>
    public const string Injection = "I can't act on that message as written. Ask the question again in plain terms.";
    /// <summary>Only a pending checkpoint can be confirmed.</summary>
    public const string NothingPending = "There is nothing waiting for your confirmation.";
    /// <summary>A new ordinary question drops the prior preview.</summary>
    public const string Dropped = "_The change I previewed earlier was dropped; nothing was changed. Ask again if you still want it._";
    /// <summary>Prepare is not a successful write.</summary>
    public const string ConfirmHint = "Reply **confirm** to apply this change, or **cancel** to drop it.";
    /// <summary>A dependency failure never becomes an empty numerical answer.</summary>
    public const string GatewayDown = "The calculation service did not answer, so I can't give a figure. Nothing has been changed.";
    /// <summary>Provider errors before a tool may degrade to deterministic reads.</summary>
    public const string ModelDown = "_The language model is unavailable, so this is the platform's own answer without commentary._";
    /// <summary>Guarded blocks remain valid if commentary is discarded.</summary>
    public const string Withheld = "_The commentary was withheld because it could not be verified against the engine's figures._";
    /// <summary>Read deadlines explicitly state that no result was obtained.</summary>
    public const string TimedOut = "That took too long, so I stopped. Nothing has been changed; try again.";
    /// <summary>A read pack cannot imply an approved change.</summary>
    public const string ReviewNext = "_This is the review pack's read-only position. Ask for a what-if (a location and a size), a question about the data, or to walk through the calculation to go deeper; any change is previewed and needs your confirmation._";

    /// <summary>Only exact command phrases may bypass planning and resume a checkpoint.</summary>
    public static string? Command(string text) => text.Trim().ToLowerInvariant().TrimEnd('.', '!').Trim() switch
    {
        "confirm" or "yes, apply" or "yes apply" => "confirm",
        "cancel" => "cancel",
        _ => null,
    };

    /// <summary>A resolver's ordered candidates, not a model's invented client, are shown.</summary>
    public static string Clarify(string kind, string reason, JsonArray? candidates = null)
    {
        if (kind == "year") { return "Which tax year do you mean?"; }
        if (kind != "client") { return string.IsNullOrEmpty(reason) ? "I need a little more to go on." : reason; }
        var choices = candidates ?? [];
        var lines = choices.Select((node, index) => $"{index + 1}) {node?["name"]?.ToString() ?? "Account " + node?["client_id"]}");
        return string.Join("\n\n", new[]
        {
            "Which client do you mean?" + (string.IsNullOrEmpty(reason) ? "" : $" ({reason})"),
            string.Join("\n", lines),
            choices.Count == 0 ? "Tell me the client's name." : "Reply with the number.",
        }.Where(part => part.Length != 0));
    }

    /// <summary>Only a sanitized dependency message may be used, never a raw transport exception.</summary>
    public static string Failure(string? code, string? message) => code switch
    {
        null => "I couldn't answer that.",
        "gateway_unreachable" or "timeout" or "api_unreachable" or "api_error" or "bad_response" => GatewayDown,
        "unauthenticated" or "caller_not_allowed" or "missing_scope" or "mixed_token" or "tenant_mismatch" or "invalid_acting_user" =>
            "The channel gateway refused this orchestrator's credentials, so I can't reach the calculation service.",
        "rate_limited" => "You're asking quickly. Wait a moment and try again.",
        "invalid_arguments" => $"I need a little more to run that: {message}",
        _ => $"I couldn't answer that: {(string.IsNullOrEmpty(message) ? code.Replace('_', ' ') : message).TrimEnd('.')}.",
    };
}
