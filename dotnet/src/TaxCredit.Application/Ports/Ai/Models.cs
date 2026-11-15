using System.Text.Json;

namespace TaxCredit.Application.Ports.Ai;

/// <summary>The job for which a model is selected, independent of provider.</summary>
public enum ModelRole
{
    /// <summary>Selects deterministic capabilities, not figures.</summary>
    Router,
    /// <summary>Describes supplied engine facts.</summary>
    Narrator,
    /// <summary>Interprets a supplied analysis brief.</summary>
    Analysis
}
/// <summary>Configuration readiness and runtime health are distinct.</summary>
public enum ProviderState
{
    /// <summary>Configured to accept requests.</summary>
    Ready,
    /// <summary>Initialization has not finished.</summary>
    Warming,
    /// <summary>Available with a stated limitation.</summary>
    Degraded,
    /// <summary>Temporarily unable to answer.</summary>
    Unavailable,
    /// <summary>Explicitly disabled.</summary>
    Disabled
}
/// <summary>A safe status without endpoint, credential or upstream detail.</summary>
public sealed record ProviderStatus(string Name, ProviderState State, string Detail = "");
/// <summary>A configured provider/model pair.</summary>
public sealed record ModelRef(string Provider, string Model);

/// <summary>Instructions are injected by the composition root, never chosen by this runtime.</summary>
public sealed class AgentSpec(string name, string instructions, ModelRole role = ModelRole.Narrator,
    double? temperature = 0.2, string? version = null)
{
    /// <summary>The registered definition key.</summary>
    public string Name { get; } = name;
    /// <summary>Versioned instructions supplied by the root.</summary>
    public string Instructions { get; } = instructions;
    /// <summary>The selection role.</summary>
    public ModelRole Role { get; } = role;
    /// <summary>Optional sampling parameter, omitted for unsupported models.</summary>
    public double? Temperature { get; } = temperature;
    /// <summary>The caller's immutable definition version.</summary>
    public string? Version { get; } = version;
    /// <inheritdoc/>
    public override string ToString() => "AgentSpec(instructions=<redacted>)";
}

/// <summary>An unframed event; the host owns SSE and response rendering.</summary>
public abstract record ModelEvent;
/// <summary>Generated prose, never a calculation.</summary>
public sealed record TextDelta(string Text) : ModelEvent
{
    /// <inheritdoc/>
    public override string ToString() => "TextDelta(<redacted>)";
}
/// <summary>A request to the caller, never executed by the provider runtime.</summary>
public sealed record ToolCall(string Id, string Name, string Arguments) : ModelEvent
{
    /// <inheritdoc/>
    public override string ToString() => "ToolCall(<redacted>)";
}
/// <summary>Provider-reported or explicitly estimated token consumption.</summary>
public sealed record ModelUsage(int? InputTokens = null, int? OutputTokens = null, bool Estimated = false) : ModelEvent
{
    /// <summary>Both directions, treating absent counts as zero.</summary>
    public long Total => (long)(InputTokens ?? 0) + (OutputTokens ?? 0);
}
/// <summary>The final answering provider with ordered attempted hops.</summary>
public sealed record StreamEnd(string Provider, string? Model = null, string? AgentVersion = null,
    IReadOnlyList<string>? Hops = null, string? FinishReason = null) : ModelEvent
{
    /// <summary>Whether another provider was attempted first.</summary>
    public bool FallbackUsed => Hops?.Count > 1;
}
/// <summary>A bare-model function schema; agents never offer these.</summary>
public sealed record ToolSpec(string Name, string Description, JsonElement Parameters)
{
    /// <inheritdoc/>
    public override string ToString() => "ToolSpec(<redacted>)";
}
/// <summary>A chat-completions message without HTTP knowledge.</summary>
public sealed record ChatMessage(string Role, string Content = "", string? ToolCallId = null,
    IReadOnlyList<ToolCall>? ToolCalls = null)
{
    /// <inheritdoc/>
    public override string ToString() => "ChatMessage(content=<redacted>)";
}

/// <summary>Trusted facts travel separately so reader text cannot replace the fallback's figures.</summary>
public sealed class NarrationRequest(AgentSpec spec, string prompt, string principal = "anonymous",
    JsonElement? trustedFacts = null, Func<string>? callerFallback = null)
{
    /// <summary>The trusted registered definition.</summary>
    public AgentSpec Spec { get; } = spec;
    /// <summary>The assembled brief; never logged.</summary>
    public string Prompt { get; } = prompt;
    /// <summary>The budget identity; never emitted in telemetry.</summary>
    public string Principal { get; } = principal;
    /// <summary>A detached copy of engine-produced facts.</summary>
    public JsonElement? TrustedFacts { get; } = trustedFacts?.Clone();
    /// <summary>Caller-controlled deterministic fallback when there are no facts.</summary>
    public Func<string>? CallerFallback { get; } = callerFallback;
    /// <inheritdoc/>
    public override string ToString() => "NarrationRequest(prompt=<redacted>, principal=<redacted>)";
}

/// <summary>A provider-neutral bare model request.</summary>
public sealed class ChatRequest(string model, IReadOnlyList<ChatMessage> messages,
    double? temperature = null, IReadOnlyList<ToolSpec>? tools = null)
{
    /// <summary>The configured model/deployment name.</summary>
    public string Model { get; } = model;
    /// <summary>Ordered messages, never logged.</summary>
    public IReadOnlyList<ChatMessage> Messages { get; } = messages;
    /// <summary>Optional sampling parameter.</summary>
    public double? Temperature { get; } = temperature;
    /// <summary>Functions the caller may implement, not the runtime.</summary>
    public IReadOnlyList<ToolSpec> Tools { get; } = tools ?? [];
    /// <inheritdoc/>
    public override string ToString() => "ChatRequest(messages=<redacted>)";
}
