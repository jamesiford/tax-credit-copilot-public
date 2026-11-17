using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Ai.Telemetry;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;
using ModelUsage = TaxCredit.Application.Ports.Ai.ModelUsage;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Actual SDK clients retain W1 role chains, pre-output fallback, guards, budgets and resilience.</summary>
public sealed class FrameworkModelRouter : IChatClient
{
    private readonly AsyncLocal<Frame?> _current = new();
    private readonly ModelRouter _router;
    private readonly Func<string> _principal;
    private readonly IReadOnlyDictionary<string, IChatClient> _clients;

    /// <summary>Registration never constructs a missing provider or silently substitutes Foundry.</summary>
    public FrameworkModelRouter(IReadOnlyDictionary<string, IChatClient> clients,
        IReadOnlyDictionary<ModelRole, IReadOnlyList<string>> chains, ITokenBudget budget,
        AiRuntimeOptions options, Func<string>? principal = null, IAiTelemetry? telemetry = null,
        IReadOnlyDictionary<string, bool>? supportsTools = null)
    {
        options.Resilience.Validate();
        if (chains.Values.Any(chain => chain.Count == 0 || chain.Any(name => !clients.ContainsKey(name))))
        {
            throw new ModelException(ModelErrorKind.Configuration, "unregistered_chain_provider");
        }
        _clients = clients;
        _principal = principal ?? (() => "anonymous");
        var registry = new ProviderRegistry();
        foreach (var (name, client) in clients)
        {
            registry.Register(name, () => new RequestRuntime(name, client, _current,
                supportsTools?.GetValueOrDefault(name, true) ?? true));
        }
        var observations = telemetry ?? new ActivityAiTelemetry(clients.Keys.Concat(["channel-router", "channel-narrator", "channel-analysis"]));
        _router = new ModelRouter(registry, chains, runtime =>
            AiRegistration.BuildRuntime(runtime, budget, observations, options with { InjectionGuard = false }));
    }

    /// <inheritdoc/>
    public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var snapshot = messages.ToArray();
        var role = options?.AdditionalProperties?["tcc.role"] is ModelRole chosen ? chosen : ModelRole.Narrator;
        var request = new NarrationRequest(new AgentSpec("channel-" + role.ToString().ToLowerInvariant(), "", role, null),
            ModelRequestText.Build(snapshot, options), _principal());
        var prior = _current.Value;
        _current.Value = new(snapshot, options);
        try
        {
            var content = new List<AIContent>();
            UsageDetails? usage = null;
            string? model = null;
            await foreach (var item in _router.Chain(role).StreamAsync(request, cancellationToken).ConfigureAwait(false))
            {
                switch (item)
                {
                    case TextDelta text: content.Add(new TextContent(text.Text)); break;
                    case ToolCall call:
                        var args = JsonSerializer.Deserialize<Dictionary<string, object?>>(call.Arguments)
                            ?? throw new ModelException(ModelErrorKind.Unavailable, "invalid_tool_arguments");
                        content.Add(new FunctionCallContent(call.Id, call.Name, args));
                        break;
                    case ModelUsage counted:
                        usage = new UsageDetails { InputTokenCount = counted.InputTokens, OutputTokenCount = counted.OutputTokens };
                        break;
                    case StreamEnd end: model = end.Model; break;
                }
            }
            return new ChatResponse(new ChatMessage(ChatRole.Assistant, content)) { Usage = usage, ModelId = model };
        }
        finally { _current.Value = prior; }
    }

    /// <inheritdoc/>
    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("The channel emits only completely guarded answers.");
    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null) => serviceType == typeof(ModelRouter) ? _router : null;
    /// <inheritdoc/>
    public void Dispose()
    {
        foreach (var client in _clients.Values.Distinct()) { client.Dispose(); }
    }

    private sealed record Frame(ChatMessage[] Messages, ChatOptions? Options);

    private sealed class RequestRuntime(string name, IChatClient client, AsyncLocal<Frame?> current, bool supportsTools) : IAgentRuntime
    {
        public string Name => name;
        public bool ReadyFor(string agentName) => supportsTools || current.Value?.Options?.Tools is not { Count: > 0 };
        public string? VersionOf(string agentName) => null;
        public ProviderStatus Status() => new(name, ProviderState.Ready);
        public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var frame = current.Value ?? throw new ModelException(ModelErrorKind.Configuration, "missing_framework_request");
            ChatResponse response;
            try { response = await client.GetResponseAsync(frame.Messages, frame.Options, cancellationToken).ConfigureAwait(false); }
            catch (System.ClientModel.ClientResultException error)
            {
                var kind = error.Status switch
                {
                    401 or 403 => ModelErrorKind.Authentication,
                    429 => ModelErrorKind.RateLimited,
                    >= 500 => ModelErrorKind.Unavailable,
                    _ => ModelErrorKind.BadRequest,
                };
                throw new ModelException(kind, "foundry_request_failed");
            }
            catch (HttpRequestException)
            {
                throw new ModelException(ModelErrorKind.Unavailable, "model_transport_failed");
            }
            foreach (var content in response.Messages.SelectMany(message => message.Contents))
            {
                if (content is TextContent text) { yield return new TextDelta(text.Text); }
                else if (content is FunctionCallContent call)
                {
                    yield return new ToolCall(call.CallId, call.Name, JsonSerializer.Serialize(call.Arguments));
                }
            }
            if (response.Usage is { } usage)
            {
                yield return new ModelUsage(checked((int?)usage.InputTokenCount), checked((int?)usage.OutputTokenCount));
            }
            yield return new StreamEnd(name, response.ModelId);
        }
    }
}

internal static class ModelRequestText
{
    internal static string Build(IEnumerable<ChatMessage> messages, ChatOptions? options)
    {
        var text = new StringBuilder(options?.Instructions);
        foreach (var message in messages)
        {
            text.AppendLine(message.Role.Value);
            foreach (var content in message.Contents)
            {
                text.AppendLine(content switch
                {
                    TextContent value => value.Text,
                    FunctionCallContent call => call.Name + JsonSerializer.Serialize(call.Arguments),
                    FunctionResultContent result => JsonSerializer.Serialize(result.Result),
                    _ => "",
                });
            }
        }
        foreach (var tool in options?.Tools?.OfType<AIFunction>() ?? [])
        {
            text.AppendLine(tool.Name).AppendLine(tool.Description).AppendLine(tool.JsonSchema.GetRawText());
        }
        return text.ToString();
    }
}
