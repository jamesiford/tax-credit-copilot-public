using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>Some portal intents require richer targeting than the offered channel capability schema.</summary>
public interface IChatIntentCollaborator
{
    /// <summary>Names either simulate (explicit worksite resolution) or multi_state (no excluded programmes).</summary>
    string Intent { get; }
    /// <summary>Returns a canonical capability envelope, including its user-only fact names.</summary>
    ValueTask<JsonObject> ReadAsync(ChatQuery query, CancellationToken cancellationToken);
}

/// <summary>Chat uses the same authorized capability boundary as HTTP, never an internal HTTP request.</summary>
public sealed class CapabilityChatFacts(CapabilityService capabilities,
    IEnumerable<IChatIntentCollaborator> collaborators) : IChatFactSource
{
    /// <inheritdoc />
    public async ValueTask<JsonObject> ReadAsync(string intent, ChatQuery query, CancellationToken cancellationToken)
    {
        if (intent is "simulate" or "multi_state")
        {
            var collaborator = collaborators.SingleOrDefault(c => c.Intent == intent);
            if (collaborator is not null) { return await collaborator.ReadAsync(query, cancellationToken).ConfigureAwait(false); }
            var dependency = intent == "simulate" ? "ReadsCalc.ResolveChatWorksiteSimulation" : "ReadsCalc.DiscoverAllPrograms";
            throw new AiFactException($"This answer is unavailable: {dependency} is not bound.", dependency);
        }
        var tool = intent switch
        {
            "book" => "book_rank",
            "situation" => "client_situation",
            "eligibility" => "client_eligibility",
            "at_risk" => "client_at_risk",
            "trend" => "client_trend",
            "discovery" => "client_discovery",
            "explain" => "calc_walkthrough",
            _ => throw new AiFactException("The requested chat capability is not supported.")
        };
        var args = Arguments(intent, query);
        try { return await capabilities.InvokeAsync(tool, args, cancellationToken: cancellationToken).ConfigureAwait(false); }
        catch (CapabilityException error) { throw new AiFactException(error.Message, tool); }
    }

    private static JsonObject Arguments(string intent, ChatQuery query)
    {
        if (intent == "book") { return new JsonObject { ["limit"] = 8 }; }
        var args = new JsonObject { ["client_id"] = query.ClientId };
        if (intent == "trend") { return args; }
        if (intent == "situation") { args["year"] = query.TaxYear; return args; }
        args["tax_year"] = query.TaxYear;
        args["state"] = query.State ?? "GA";
        if (intent != "discovery")
        {
            // The portal's established eligibility brief deliberately selects Pay Period (D-05).
            args["method"] = intent == "eligibility" ? "pay_period" : query.Method;
        }
        return args;
    }
}
