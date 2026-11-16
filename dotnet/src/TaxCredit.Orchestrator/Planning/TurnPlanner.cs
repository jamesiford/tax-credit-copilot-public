using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Orchestrator.Composition;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Turns;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Planning;

/// <summary>Only tool selection varies; execution, projection and final composition stay shared.</summary>
public sealed class TurnPlanner(ModelToolCatalog catalog, FrameworkToolLoop loop,
    IChatClient? model = null, bool supportsTools = true, IReferenceSource? knowledge = null, bool knowledgeEnabled = false,
    int knowledgeTop = 3)
{
    /// <summary>Planning returns untrusted narration separately from the evidence that will judge it.</summary>
    public async Task<PlannedTurn> PlanAsync(ToolSession turn, CancellationToken cancellationToken)
    {
        var plan = new PlannedTurn(model is null ? "keywords" : supportsTools ? "tools" : "json");
        if (PromptInjectionGuard.Scan(turn.Question).Count != 0)
        {
            plan.Mode = "keywords";
            plan.Injection = true;
            await KeywordsAsync(turn, cancellationToken).ConfigureAwait(false);
            return plan;
        }
        if (PlannerPrompts.WantsReview(turn.Question))
        {
            plan.Mode = "review_pack";
            if (ReaderWords.Years(turn.Question).Count == 0 && turn.State.TaxYear is null)
            {
                await loop.RunOneAsync(turn, "client_eligibility", new JsonObject(), cancellationToken).ConfigureAwait(false);
                return plan;
            }
            foreach (var name in PlannerPrompts.ReviewTools)
            {
                await loop.RunOneAsync(turn, name, new JsonObject(), cancellationToken).ConfigureAwait(false);
                if (turn.Clarification is not null) { break; }
            }
            return plan;
        }
        if (model is null) { await KeywordsAsync(turn, cancellationToken).ConfigureAwait(false); return plan; }
        if (EgressGuard.IdentifierRules(turn.Question).Count != 0)
        {
            plan.Mode = "keywords";
            plan.Degraded = true;
            await KeywordsAsync(turn, cancellationToken).ConfigureAwait(false);
            return plan;
        }
        using var traced = new TracedModelClient(model, plan);
        try
        {
            plan.Reference = await ReferenceContext.RetrieveAsync(knowledgeEnabled, knowledge, turn.Question,
                top: knowledgeTop, cancellationToken: cancellationToken).ConfigureAwait(false);
            if (supportsTools)
            {
                var routing = RoutingContext(turn) + "\n" + plan.Reference.ModelContext();
                plan.Narration = await loop.RunAsync(traced, turn, routing,
                    PlannerPrompts.Planner + "\n" + PlannerPrompts.Narrator, turn.MaxCalls, cancellationToken).ConfigureAwait(false);
            }
            else { await JsonAsync(traced, turn, plan, cancellationToken).ConfigureAwait(false); }
        }
        catch (Exception error) when (IsModelFailure(error, cancellationToken))
        {
            plan.Narration = null;
            plan.Reference = ReferenceContext.Disabled;
            plan.Degraded = true;
            if (turn.Runs.Count == 0)
            {
                plan.Mode = "keywords";
                await KeywordsAsync(turn, cancellationToken).ConfigureAwait(false);
            }
        }
        return plan;
    }

    private async Task KeywordsAsync(ToolSession turn, CancellationToken cancellationToken)
    {
        foreach (var name in PlannerPrompts.Keywords(turn.Question).Take(turn.MaxCalls))
        {
            await loop.RunOneAsync(turn, name, new JsonObject(), cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task JsonAsync(TracedModelClient client, ToolSession turn, PlannedTurn plan, CancellationToken cancellationToken)
    {
        var tools = new JsonArray(catalog.Definitions.OfType<AIFunction>().Select(function => (JsonNode)new JsonObject
        {
            ["name"] = function.Name,
            ["description"] = function.Description,
            ["schema"] = JsonNode.Parse(function.JsonSchema.GetRawText()),
        }).ToArray());
        var messages = new List<ChatMessage>
        {
            new(ChatRole.System, PlannerPrompts.Planner + "\n" + PlannerPrompts.JsonPlan + "\nTOOLS:\n" + tools.ToJsonString()),
            new(ChatRole.User, RoutingContext(turn)),
        };
        var lookedUp = await RoundAsync(client, messages, turn, cancellationToken).ConfigureAwait(false);
        if (lookedUp.Count != 0 && turn.Runs.All(run => run.IsLookup) && turn.Clarification is null)
        {
            messages.Add(new(ChatRole.User, "LOOKUP RESULTS (names only):\n" + lookedUp.ToJsonString()));
            await RoundAsync(client, messages, turn, cancellationToken).ConfigureAwait(false);
        }
        if (turn.Runs.Count != 0 && turn.Clarification is null)
        {
            var brief = ModelBrief.Build(turn.Question, turn.Runs, fenced: true);
            var answer = await client.GetResponseAsync(
                [new(ChatRole.System, PlannerPrompts.Narrator + "\n" + plan.Reference.ModelContext()), new(ChatRole.User, "JSON:\n" + brief.ToJsonString())],
                new ChatOptions { AdditionalProperties = new() { ["tcc.role"] = ModelRole.Narrator } },
                cancellationToken: cancellationToken).ConfigureAwait(false);
            plan.Narration = answer.Text;
        }
    }

    private async Task<JsonObject> RoundAsync(TracedModelClient client, List<ChatMessage> messages, ToolSession turn, CancellationToken cancellationToken)
    {
        var response = await client.GetResponseAsync(messages,
            new ChatOptions { AdditionalProperties = new() { ["tcc.role"] = ModelRole.Narrator } },
            cancellationToken: cancellationToken).ConfigureAwait(false);
        var lookedUp = new JsonObject();
        foreach (var (name, args) in Parse(response.Text, turn.MaxCalls))
        {
            var before = turn.Runs.Count;
            await loop.RunOneAsync(turn, name, args, cancellationToken).ConfigureAwait(false);
            foreach (var run in turn.Runs.Skip(before).Where(run => run.IsLookup))
            {
                lookedUp[run.Name] = ModelBrief.Answer(run, ModelBrief.Build(turn.Question, [run]))["result"]?.DeepClone();
            }
        }
        return lookedUp;
    }

    /// <summary>Names remain unfiltered until the common refusal/budget path sees them.</summary>
    public static IReadOnlyList<(string Name, JsonObject Arguments)> Parse(string text, int limit)
    {
        var start = text.IndexOf('{');
        var end = text.LastIndexOf('}');
        if (start < 0 || end < start) { return []; }
        JsonNode? document;
        try { document = JsonNode.Parse(text[start..(end + 1)]); }
        catch (JsonException) { return []; }
        if (document is not JsonObject obj || obj["tools"] is not JsonArray tools) { return []; }
        var result = new List<(string, JsonObject)>();
        foreach (var tool in tools)
        {
            var name = tool is JsonObject item ? item["tool"] : tool;
            if (name is not JsonValue value || !value.TryGetValue<string>(out var word)) { continue; }
            result.Add((word, tool is JsonObject row && row["args"] is JsonObject args ? (JsonObject)args.DeepClone() : new()));
            if (result.Count >= limit) { break; }
        }
        return result;
    }

    private static string RoutingContext(ToolSession turn) => "UNTRUSTED reader question:\n" + turn.Question +
        "\nEND UNTRUSTED\nUNTRUSTED routing history:\n" +
        new JsonArray(turn.State.History.Select(entry => (JsonNode)entry.DeepClone()).ToArray()).ToJsonString() + "\nEND UNTRUSTED";

    private static bool IsModelFailure(Exception error, CancellationToken token) =>
        error is ModelException or HttpRequestException or TimeoutException or System.ClientModel.ClientResultException ||
        error is OperationCanceledException && !token.IsCancellationRequested;
}

/// <summary>Evidence is owned by the tool session, never by a returned model transcript.</summary>
public sealed class PlannedTurn(string mode)
{
    /// <summary>The actual planner, not a guessed model capability.</summary>
    public string Mode { get; set; } = mode;
    /// <summary>Raw commentary is never a finished response.</summary>
    public string? Narration { get; set; }
    /// <summary>A provider was actually asked, even if it failed.</summary>
    public bool ModelCalled { get; set; }
    /// <summary>A failed narrator is discarded wholesale.</summary>
    public bool Degraded { get; set; }
    /// <summary>Injection screening happened before provider work.</summary>
    public bool Injection { get; set; }
    /// <summary>A digest of every actual request; no prompt or row is retained in the audit report.</summary>
    public string? PromptSha256 { get; set; }
    /// <summary>The answering deployment label, never an endpoint or credential.</summary>
    public string? Model { get; set; }
    /// <summary>Reference prose is never inserted into trusted engine facts.</summary>
    public ReferenceContext Reference { get; set; } = ReferenceContext.Disabled;
}
