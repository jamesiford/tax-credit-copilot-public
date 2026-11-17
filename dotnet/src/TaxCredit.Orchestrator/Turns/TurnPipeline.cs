using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Composition;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Planning;
using TaxCredit.Orchestrator.Workflow;

namespace TaxCredit.Orchestrator.Turns;

/// <summary>Attribution, checkpoint decisions, tools, composition and narration audit form one serialized turn.</summary>
public sealed class TurnPipeline(IGatewayClient gateway, ModelToolCatalog catalog, TurnPlanner planner,
    ConversationStore store, WorkflowBridge workflow, TurnOptions? options = null,
    ILogger<TurnPipeline>? logger = null)
{
    private static readonly Action<ILogger, string, Exception?> AuditFailed = LoggerMessage.Define<string>(
        LogLevel.Error, new EventId(1, "narration_audit_failed"), "Narration audit failed: {Code}");
    private readonly TurnOptions _options = options ?? new();
    private int _auditFailures;
    private string? _lastAuditError;
    /// <summary>Audit failure counts are safe debug metadata, never a reason to hide an answer.</summary>
    public int AuditFailures => Volatile.Read(ref _auditFailures);
    /// <summary>Only a controlled gateway code is retained.</summary>
    public string? LastAuditError => Volatile.Read(ref _lastAuditError);
    /// <summary>No identity means no state access, model request, resolver or write.</summary>
    public Task<TurnReply> HandleAsync(string text, ActingIdentity? identity, CancellationToken cancellationToken = default) =>
        identity is null ? Task.FromResult(new TurnReply(Replies.Unattributed, "refusal")) :
            workflow.AsAsync(identity, () => AttributedAsync(text, identity, cancellationToken));

    private async Task<TurnReply> AttributedAsync(string text, ActingIdentity identity, CancellationToken cancellationToken)
    {
        var key = identity.TenantId + ":" + identity.Oid + ":" + identity.ConversationId;
        using var lease = await store.AcquireAsync(key, cancellationToken).ConfigureAwait(false);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(_options.TurnTimeout);
        if (lease.IsNew)
        {
            await workflow.RespondAsync(identity, "__expired_conversation__", deadline.Token).ConfigureAwait(false);
        }
        var prior = await workflow.RespondAsync(identity, text, deadline.Token).ConfigureAwait(false);
        if (Replies.Command(text) is not null || prior.Status is not (WriteStatus.NothingPending or WriteStatus.Dropped))
        {
            return CommitReply(prior);
        }
        try
        {
            var reply = await AnswerAsync(text, identity, lease.State, deadline.Token).ConfigureAwait(false);
            return prior.Status == WriteStatus.Dropped ? reply with { Text = reply.Text + "\n\n" + Replies.Dropped } : reply;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return new TurnReply(Replies.TimedOut, "failure");
        }
    }

    private async Task<TurnReply> AnswerAsync(string text, ActingIdentity identity, ConversationState state, CancellationToken ct)
    {
        var asked = state.Question;
        var choices = state.Candidates;
        state.Question = "";
        state.Candidates = [];
        int? chosen = null;
        if (choices.Count != 0 && text.Trim().All(char.IsAsciiDigit) && int.TryParse(text.Trim(), out var number))
        {
            if (number < 1 || number > choices.Count)
            {
                state.Candidates = choices;
                state.Question = asked;
                return new TurnReply(Replies.Clarify("client", "", choices), "clarify");
            }
            chosen = state.ClientId = ReaderWords.Integer(choices[number - 1]?["client_id"]);
            text = asked.Length == 0 ? text : asked;
        }
        else if (choices.Count == 0 && PlannerPrompts.WantsReview(asked) &&
            text.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries).Length == 1 && ReaderWords.Years(text).Count != 0)
        {
            text = asked + " " + text.Trim();
        }
        var session = new ToolSession(gateway, identity, state, text, catalog,
            PlannerPrompts.WantsReview(text) ? 6 : _options.MaxToolCalls,
            (name, args, token) => workflow.PrepareAsync(identity, name, args, token))
        { ClientId = chosen };
        var planned = await planner.PlanAsync(session, ct).ConfigureAwait(false);
        state.Remember("user", text);
        if (session.Clarification is { } clarify)
        {
            if (clarify.Kind == "client") { state.Candidates = clarify.Candidates; state.Question = text; }
            else if (clarify.Kind == "year" && PlannerPrompts.WantsReview(text)) { state.Question = text; }
            var reply = new TurnReply(Replies.Clarify(clarify.Kind, clarify.Reason, clarify.Candidates), "clarify", planned.Mode,
                ModelCalled: planned.ModelCalled, Runs: session.Runs);
            await AuditAsync(identity, session, planned, null, reply.Text, ct).ConfigureAwait(false);
            return reply;
        }
        if (session.Runs.Count == 0)
        {
            var problem = session.Problems.FirstOrDefault();
            var failed = problem is not null || session.Refused.Count != 0;
            var reply = new TurnReply(failed ? Replies.Failure(problem?.Code, problem?.Message) : Replies.Help,
                failed ? "failure" : "help", planned.Mode, ModelCalled: planned.ModelCalled, Runs: session.Runs);
            await AuditAsync(identity, session, planned, null, reply.Text, ct).ConfigureAwait(false);
            return reply;
        }
        var composition = new CompositionPlan(text, session.Runs, allowedHosts: _options.OutputAllowedHosts, reference: planned.Reference);
        composition.Narrate(planned.Narration);
        if (planned.Degraded) { composition.FallBack(); }
        var composed = composition.ComposedFor();
        var parts = new List<string> { composed.Text };
        if (planned.ModelCalled && !string.IsNullOrEmpty(planned.Narration) && !composed.NarrationUsed) { parts.Add(Replies.Withheld); }
        if (planned.Degraded) { parts.Add(Replies.ModelDown); }
        if (session.Problems.FirstOrDefault() is { } failure) { parts.Add(Replies.Failure(failure.Code, failure.Message)); }
        if (session.HasPrepared) { parts.Add(Replies.ConfirmHint); }
        if (planned.Mode == "review_pack") { parts.Add(Replies.ReviewNext); }
        var finished = string.Join("\n\n", parts.Where(part => part.Length != 0));
        state.Remember("assistant", finished);
        await AuditAsync(identity, session, planned, composed, finished, ct).ConfigureAwait(false);
        return new TurnReply(finished, "answer", planned.Mode, composed.Guard.Status, composed.NarrationUsed, planned.ModelCalled, session.Runs);
    }

    private TurnReply CommitReply(WriteResult outcome)
    {
        if (outcome.Status == WriteStatus.NothingPending) { return new(Replies.NothingPending, "commit_refused"); }
        if (outcome.Status is WriteStatus.Cancelled or WriteStatus.Dropped) { return new("Cancelled. Nothing was changed.", "cancel"); }
        if (outcome.Status == WriteStatus.Expired) { return new("That preview has expired, so nothing was changed. Ask again to get a fresh preview.", "commit_refused"); }
        if (outcome.Status == WriteStatus.Unknown)
        {
            return new("The calculation service did not confirm the change, so I can't say whether it was made. Check the claim record before asking again; I won't retry on my own.", "commit_refused");
        }
        var reply = WorkflowBridge.Reply(outcome);
        if (outcome.Status == WriteStatus.Committed && reply.ToCapabilityResult(reply.Body["tool"]?.ToString() ?? "commit") is { } result)
        {
            var runs = new List<ToolRun> { new(result.Tool, new JsonObject(), result, result.Tool) };
            foreach (var followUp in outcome.FollowUps)
            {
                var envelope = new GatewayReply(followUp.Reply.StatusCode,
                    JsonNode.Parse(followUp.Reply.Body.GetRawText())!.AsObject());
                if (envelope.ToCapabilityResult(followUp.Tool) is { } linked)
                {
                    runs.Add(new ToolRun(followUp.Tool, new JsonObject(), linked, followUp.Tool));
                }
            }
            var text = GuardedReplyComposer.ComposeReply("", runs, null, allowedHosts: _options.OutputAllowedHosts).Text;
            if (outcome.Note.Length != 0) { text += "\n\n" + outcome.Note; }
            return new(text, "commit", Runs: runs);
        }
        return new(Replies.Failure(reply.ErrorCode, reply.ErrorMessage), "commit_refused");
    }

    private async Task AuditAsync(ActingIdentity identity, ToolSession session, PlannedTurn planned,
        ComposedReply? composed, string text, CancellationToken ct)
    {
        if (!planned.ModelCalled) { return; }
        var report = new JsonObject
        {
            ["conversation_id"] = identity.ConversationId[..Math.Min(identity.ConversationId.Length, 100)],
            ["agent_name"] = _options.AgentName,
            ["agent_version"] = _options.AgentVersion,
            ["model"] = planned.Model ?? "",
            ["prompt_sha256"] = planned.PromptSha256,
            ["tool_names"] = new JsonArray(session.Runs.Select(run => run.Name).Distinct(StringComparer.Ordinal)
                .Order(StringComparer.Ordinal).Select(name => (JsonNode?)JsonValue.Create(name)).ToArray()),
            ["guard_status"] = composed?.Guard.Passed == false ? "rejected" : "pass",
            ["violations_count"] = composed?.Guard.Violations.Count ?? 0,
            ["output_summary"] = $"mode={planned.Mode}; narration_used={composed?.NarrationUsed == true}; tools={session.Runs.Count}; chars={text.Length}",
        };
        var reply = await gateway.ReportNarrationAsync(identity, report, ct).ConfigureAwait(false);
        Volatile.Write(ref _lastAuditError, reply.Ok ? null : reply.ErrorCode);
        if (!reply.Ok)
        {
            Interlocked.Increment(ref _auditFailures);
            if (logger is not null) { AuditFailed(logger, reply.ErrorCode, null); }
        }
    }
}

/// <summary>Configuration is bounded independently of a model's proposed plan.</summary>
public sealed record TurnOptions(int MaxToolCalls = 8, string AgentName = "tcc-channel-orchestrator", string AgentVersion = "0")
{
    /// <summary>A lost upstream reply cannot hold an operator turn forever.</summary>
    public TimeSpan TurnTimeout { get; init; } = TimeSpan.FromSeconds(90);
    /// <summary>Only configured hosts may appear in model-authored links.</summary>
    public IReadOnlyList<string> OutputAllowedHosts { get; init; } = [];
}

/// <summary>A deterministic turn result separates model participation from trusted response text.</summary>
public sealed record TurnReply(string Text, string Kind, string Mode = "none", string GuardStatus = "n/a",
    bool NarrationUsed = false, bool ModelCalled = false, IReadOnlyList<ToolRun>? Runs = null);
