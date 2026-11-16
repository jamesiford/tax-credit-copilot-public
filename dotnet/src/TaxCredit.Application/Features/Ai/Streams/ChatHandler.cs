using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Application.Features.Ai.Streams;

/// <summary>One request can answer several intents, but has exactly one terminal event.</summary>
public sealed class ChatHandler(IChatClientSource clients, ChatPlanner planner, IChatFactSource facts,
    IAiNarrator narrator, IApiPrincipalAccessor principals, IAiTelemetry telemetry)
{
    /// <summary>Defers execution so the HTTP request owns the complete stream lifetime.</summary>
    public ValueTask<IAsyncEnumerable<AiFrame>> Handle(ChatQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(Stream(request, cancellationToken));

    private async IAsyncEnumerable<AiFrame> Stream(ChatQuery query, [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var keywordPlan = ChatRouting.KeywordIntents(query.Message);
        var clientRead = await ReadClientsAsync(cancellationToken).ConfigureAwait(false);
        if (clientRead.Failed)
        {
            yield return new("error", new { detail = "The client book for this answer is unavailable." });
            yield return new("done", new { });
            yield break;
        }
        var book = clientRead.Clients;
        var referent = book.Count > 0 ? ChatReferents.Resolve(query, book) : new(false, [], "");
        if (keywordPlan.All(i => i != "book") && referent.Clarify)
        {
            foreach (var frame in ChatClarification.Frames(query, referent, book)) { yield return frame; }
            yield return new("done", new { });
            yield break;
        }
        if (keywordPlan.All(i => i != "book") && (query.ClientId is null || query.TaxYear is null))
        {
            foreach (var frame in ChatClarification.MissingScope(query)) { yield return frame; }
            yield return new("done", new { });
            yield break;
        }
        var plan = await planner.PlanAsync(query, cancellationToken).ConfigureAwait(false);
        var ready = plan.Where(i => i == "book" || (!referent.Clarify && query.ClientId is not null && query.TaxYear is not null)).ToArray();
        var refused = plan.Except(ready, StringComparer.Ordinal).ToArray();
        yield return new("plan", new
        {
            intents = ready,
            needs_client = refused,
            capabilities = ready.ToDictionary(i => i, i => ChatRouting.Intents[i], StringComparer.Ordinal)
        });
        foreach (var intent in ready)
        {
            await foreach (var frame in Pipeline(intent, query, cancellationToken).ConfigureAwait(false)) { yield return frame; }
        }
        if (refused.Length > 0)
        {
            var frames = referent.Clarify
                ? ChatClarification.Frames(query, referent, book)
                : ChatClarification.MissingScope(query);
            foreach (var frame in frames) { yield return frame; }
        }
        yield return new("done", new { });
    }

    private async IAsyncEnumerable<AiFrame> Pipeline(string intent, ChatQuery query,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        yield return new("status", intent == "book"
            ? new JsonObject { ["phase"] = 3, ["intent"] = intent }
            : new JsonObject { ["phase"] = 3, ["intent"] = intent, ["client_id"] = query.ClientId, ["tax_year"] = query.TaxYear });
        JsonObject? envelope = null;
        string? failure = null;
        try { envelope = await facts.ReadAsync(intent, query, cancellationToken).ConfigureAwait(false); }
        catch (AiFactException error) { failure = error.Message; }
#pragma warning disable CA1031 // Client-visible errors are explicit and sanitized; telemetry contains only classification.
        catch (Exception error) when (error is not OperationCanceledException)
        {
            telemetry.Count("ai.chat_fact_failed", scope: error.GetType().Name);
            failure = "The figures for this answer are unavailable.";
        }
#pragma warning restore CA1031
        if (envelope is null)
        {
            yield return new("error", new { detail = failure });
            yield break;
        }
        yield return new("evidence", envelope.DeepClone());
        var agent = intent is "book" or "situation" or "at_risk" or "trend" ? "ClientSituationAgent" : "ReportingAgent";
        yield return new("agent_start", new { agent });
        var trusted = JsonSerializer.SerializeToElement(NarrationLanes.Trusted(envelope));
        if (!narrator.Available([agent]))
        {
            yield return new("token", new { agent, content = "The assistant is unavailable; here are the engine's figures.\n\n" + NarrationLanes.Render(envelope) });
        }
        else
        {
            var prompt = "Describe only the supplied facts for this question.\n<untrusted-question>\n" + query.Message
                + "\n</untrusted-question>\nJSON:\n" + trusted.GetRawText();
            await using var events = ModelStream.Open(() => narrator.StreamAsync(agent, prompt,
                principals.Current?.Actor ?? "anonymous", trusted, cancellationToken), telemetry, cancellationToken);
            if (events is null)
            {
                yield return new("token", new { agent, content = "The assistant is unavailable; here are the engine's figures.\n\n" + NarrationLanes.Render(envelope) });
            }
            while (events is not null)
            {
                var next = await ModelStream.MoveAsync(events, telemetry, cancellationToken).ConfigureAwait(false);
                if (next.Failed)
                {
                    yield return new("token", new { agent, content = "The assistant was interrupted; the engine's figures follow.\n\n" + NarrationLanes.Render(envelope) });
                    break;
                }
                if (!next.HasValue) { break; }
                if (events.Current is TextDelta { Text.Length: > 0 } delta)
                {
                    yield return new("token", new { agent, content = delta.Text });
                }
            }
        }
        yield return new("agent_end", new { agent });
    }

    private async ValueTask<(IReadOnlyList<ChatClient> Clients, bool Failed)> ReadClientsAsync(CancellationToken cancellationToken)
    {
        try { return (await clients.ReadAsync(cancellationToken).ConfigureAwait(false), false); }
#pragma warning disable CA1031 // A source outage is an explicit refusal, never an empty book or a guessed client.
        catch (Exception error) when (error is not OperationCanceledException)
        {
            telemetry.Count("ai.chat_clients_failed", scope: error.GetType().Name);
            return ([], true);
        }
#pragma warning restore CA1031
    }
}
