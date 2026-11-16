using System.Diagnostics;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Composition;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Planning;

namespace TaxCredit.Orchestrator.Turns;

/// <summary>One turn's ledger and rules are shared by all three planners through actual function middleware.</summary>
public sealed class ToolSession(IGatewayClient gateway, ActingIdentity identity, ConversationState state,
    string question, ModelToolCatalog catalog, int maxCalls,
    Func<string, JsonObject, CancellationToken, Task<GatewayReply>>? prepare = null) : IToolExecution
{
    private static readonly ActivitySource Traces = new("TaxCredit.Orchestrator.Tools");
    private readonly Dictionary<string, object?> _answered = new(StringComparer.Ordinal);
    private bool _resolved;

    /// <summary>The question is reader-owned, not a model's rewrite.</summary>
    public string Question { get; } = question;
    /// <summary>The state lease is held for this entire turn.</summary>
    public ConversationState State { get; } = state;
    /// <summary>Successful, full authorized envelopes stay in the person's turn ledger.</summary>
    public List<ToolRun> Runs { get; } = [];
    /// <summary>Only controlled dependency failures are retained.</summary>
    public List<ToolProblem> Problems { get; } = [];
    /// <summary>Unregistered calls are observed before the SDK rejects them.</summary>
    public List<string> Refused { get; } = [];
    /// <summary>Clarification short-circuits all later tool calls in this turn.</summary>
    public ToolClarification? Clarification { get; private set; }
    /// <summary>Attempts, not successful answers, consume the budget.</summary>
    public int Calls { get; private set; }
    /// <summary>Review packs can override the ordinary read limit.</summary>
    public int MaxCalls { get; } = maxCalls;
    /// <summary>A numbered resolver choice bypasses another resolver call.</summary>
    public int? ClientId { get; set; }
    /// <summary>A prepare is only a preview, with the secret held by the checkpoint workflow.</summary>
    public bool HasPrepared { get; private set; }

    /// <inheritdoc/>
    public async Task<object?> InvokeAsync(string name, JsonObject proposed,
        Func<JsonObject, CancellationToken, Task<object?>> forward, CancellationToken cancellationToken)
    {
        if (Calls >= MaxCalls) { return Refusal("tool_budget", "no more tools may run in this turn"); }
        Calls++;
        var spec = catalog.Find(name);
        if (spec is null) { Refused.Add(name); return Refusal("unknown_tool", "that tool may not be called"); }
        if (Clarification is not null) { return NeedsReader(); }
        var args = new JsonObject(proposed.Where(pair => pair.Value is not null)
            .Select(pair => KeyValuePair.Create(pair.Key, (JsonNode?)pair.Value!.DeepClone())));
        if (spec["schema"]!["properties"]!.AsObject().ContainsKey("client_id"))
        {
            var client = await EnsureClientAsync(cancellationToken).ConfigureAwait(false);
            if (client is null) { return NeedsReader(); }
            args["client_id"] = client;
        }
        var needed = ReaderWords.Settle(spec, args, Question, State.TaxYear);
        if (needed is not null)
        {
            Clarification = new(needed, needed == "detail" ? "How many, or by how much?" : "", []);
            return NeedsReader();
        }
        try { CapabilitySchema.Validate(spec["schema"]!.AsObject(), args); }
        catch (CapabilityException error)
        {
            Problems.Add(new(name, error.Code, error.Message));
            return Refusal(error.Code, error.Message);
        }
        var key = name + ":" + Canonical(args);
        if (_answered.TryGetValue(key, out var previous)) { return previous; }
        var methods = args["method"]?.ToString() == "both" ? new[] { "min_max", "pay_period" } : new[] { "" };
        var answers = new List<JsonObject>();
        foreach (var method in methods)
        {
            if (answers.Count != 0 && Calls >= MaxCalls) { break; }
            if (answers.Count != 0) { Calls++; }
            var settled = (JsonObject)args.DeepClone();
            if (method.Length != 0) { settled["method"] = method; }
            var reply = await forward(settled, cancellationToken).ConfigureAwait(false) as GatewayReply
                ?? throw new InvalidOperationException("The generated gateway forwarder returned an invalid reply.");
            answers.Add(Capture(name, settled, reply));
        }
        object answer = methods.Length == 1 ? answers[0] : new JsonObject
        {
            ["ok"] = answers.Any(item => item["ok"]?.GetValue<bool>() == true),
            ["tool"] = name,
            ["fact_paths"] = new JsonArray(answers.SelectMany(item => item["fact_paths"] as JsonArray ?? [])
                .Select(node => node?.DeepClone()).ToArray()),
            ["notes"] = new JsonArray(),
        };
        _answered[key] = answer;
        return answer;
    }

    /// <inheritdoc/>
    public async Task<object?> ForwardAsync(string name, JsonObject arguments, CancellationToken cancellationToken)
    {
        using var span = Traces.StartActivity("tool");
        span?.SetTag("tcc.tool", name);
        span?.SetTag("tcc.channel", identity.Channel);
        var isPrepare = catalog.Find(name)?["kind"]?.ToString() == "write_prepare";
        var reply = isPrepare && prepare is not null
            ? await prepare(name, arguments, cancellationToken).ConfigureAwait(false)
            : isPrepare ? GatewayReply.Failure("workflow_unavailable", "The confirmation workflow is unavailable.")
            : await gateway.CallToolAsync(identity, name, arguments, cancellationToken: cancellationToken).ConfigureAwait(false);
        span?.SetTag("tcc.outcome", reply.Ok ? "ok" : "error");
        if (!reply.Ok) { span?.SetTag("tcc.error_code", reply.ErrorCode); }
        HasPrepared |= isPrepare && reply.Ok;
        return reply;
    }

    /// <inheritdoc/>
    public void RefuseUnknown(string name)
    {
        if (Calls < MaxCalls) { Calls++; }
        Refused.Add(name);
    }

    /// <summary>The deterministic resolver is called once even if it fails or several tools ask.</summary>
    public async Task<int?> EnsureClientAsync(CancellationToken cancellationToken)
    {
        if (ClientId is not null || _resolved || Clarification is not null) { return ClientId; }
        _resolved = true;
        var reply = await gateway.CallToolAsync(identity, "client_resolve", new JsonObject
        {
            ["name_or_text"] = Question,
            ["history"] = new JsonArray(State.History.Select(entry => (JsonNode)entry.DeepClone()).ToArray()),
            ["current_client_id"] = State.ClientId,
        }, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (!reply.Ok) { Problems.Add(new("client_resolve", reply.ErrorCode, reply.ErrorMessage)); return null; }
        var facts = reply.Body["facts"] as JsonObject;
        var chosen = ReaderWords.Integer(facts?["client_id"]);
        if (chosen is null && facts?["clarify"]?.GetValue<bool>() == true && facts["named"] is JsonArray { Count: 1 } named)
        {
            chosen = ReaderWords.Integer(named[0]);
        }
        if (chosen is null)
        {
            Clarification = new("client", facts?["reason"]?.ToString() ?? "",
                facts?["candidates"] is JsonArray candidates ? (JsonArray)candidates.DeepClone() : []);
            return null;
        }
        return ClientId = State.ClientId = chosen;
    }

    private JsonObject Capture(string name, JsonObject args, GatewayReply reply)
    {
        if (!reply.Ok) { Problems.Add(new(name, reply.ErrorCode, reply.ErrorMessage)); return Refusal(reply.ErrorCode, reply.ErrorMessage); }
        var result = reply.ToCapabilityResult(name);
        if (result is null)
        {
            Problems.Add(new(name, "bad_response", ""));
            return Refusal("bad_response", "the capability envelope was invalid");
        }
        result.Facts.Remove("confirmation");
        if (args["tax_year"] is { } year) { State.TaxYear = ReaderWords.Integer(year); }
        var baseLabel = name + (args["method"] is { } method ? "_" + method : "");
        var label = baseLabel;
        for (var index = 2; Runs.Any(run => run.Label == label); index++) { label = $"{baseLabel}_{index}"; }
        var lookup = catalog.Find(name)?["tags"]?.AsArray().Any(node => node?.ToString() == "lookup") == true;
        var run = new ToolRun(name, args, result, label, lookup);
        Runs.Add(run);
        return ModelBrief.Answer(run, ModelBrief.Build(Question, [run]));
    }

    private JsonObject NeedsReader() => Refusal("needs_" + (Clarification?.Kind ?? "client"),
        "the reader must clarify; stop and wait");
    private static JsonObject Refusal(string code, string message) => new() { ["ok"] = false, ["error"] = code, ["message"] = message };
    private static string Canonical(JsonNode? value) => value switch
    {
        JsonObject obj => "{" + string.Join(",", obj.OrderBy(pair => pair.Key, StringComparer.Ordinal)
            .Select(pair => System.Text.Json.JsonSerializer.Serialize(pair.Key) + ":" + Canonical(pair.Value))) + "}",
        JsonArray array => "[" + string.Join(",", array.Select(Canonical)) + "]",
        _ => value?.ToJsonString() ?? "null",
    };
}

/// <summary>Only sanitized code and public message may reach the reader.</summary>
public sealed record ToolProblem(string Tool, string Code, string Message);
/// <summary>A turn cannot proceed until the reader settles this dimension.</summary>
public sealed record ToolClarification(string Kind, string Reason, JsonArray Candidates);
