using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Orchestrator.Composition;

/// <summary>One completed gateway call; its label namespaces facts, including repeated methods.</summary>
public record CompositionRun(
    string Name, JsonObject Arguments, CapabilityResult Result, string Label, bool IsLookup = false);

/// <summary>Runner-friendly name for a completed capability call.</summary>
public sealed record ToolRun : CompositionRun
{
    /// <summary>Keep full reader evidence until the deliberate model projection boundary.</summary>
    public ToolRun(string name, JsonObject args, CapabilityResult result, string label, bool isLookup = false)
        : base(name, args, result, label, isLookup) { }

    /// <summary>The settled, reader-owned arguments.</summary>
    public JsonObject Args => Arguments;
}

/// <summary>The checked body excludes the trusted identifier footer and separately fenced references.</summary>
public sealed record ComposedReply(
    string Text, string Body, string Footer, GuardResult Guard, bool NarrationUsed,
    bool BlocksVerified = true, string? Notice = null)
{
    /// <summary>Quoted, explicitly untrusted references are outside the independently checked engine body.</summary>
    public string ReferenceText { get; init; } = "";

    /// <summary>Only rule codes, not rejected prose, employee paths or nearest employee facts, enter audit.</summary>
    public IReadOnlyList<string> AuditRules => Guard.Violations.Select(item => item.Reason)
        .Distinct(StringComparer.Ordinal).ToArray();
}

/// <summary>A turn's composition is cached, never reconstructed separately by each planner.</summary>
public sealed class CompositionPlan
{
    private readonly string question;
    private readonly IReadOnlyList<CompositionRun> runs;
    private readonly IReadOnlyList<string> allowedHosts;
    private readonly Lock gate = new();
    private ReferenceContext? reference;
    private ComposedReply? composed;

    /// <summary>Capture the turn so mutations in a gateway JSON object cannot change a cached reply.</summary>
    public CompositionPlan(string question, IReadOnlyList<CompositionRun> runs,
        IReadOnlyList<string>? allowedHosts = null, ReferenceContext? reference = null)
    {
        this.question = question;
        this.runs = runs.Select(CompositionProjection.Snapshot).ToArray();
        this.allowedHosts = allowedHosts?.ToArray() ?? [];
        this.reference = reference;
    }

    /// <summary>The latest narration, never the reader's finished answer.</summary>
    public string? Narration { get; private set; }

    /// <summary>A model failure permanently discards its narration until another is supplied explicitly.</summary>
    public bool Degraded { get; private set; }

    /// <summary>New narration invalidates the previous composition.</summary>
    public void Narrate(string? narration)
    {
        lock (gate)
        {
            Narration = narration;
            composed = null;
        }
    }

    /// <summary>Every planner obtains the same checked reply through this point.</summary>
    public ComposedReply ComposedFor()
    {
        lock (gate)
        {
            return composed ??= GuardedReplyComposer.ComposeReply(question, runs, Narration, allowedHosts, reference);
        }
    }

    /// <summary>Failure after a tool call retains its evidence, not the model's partially returned prose.</summary>
    public void FallBack()
    {
        lock (gate)
        {
            Degraded = true;
            reference = null;
            Narrate(null);
        }
    }
}
