using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Configured non-Foundry providers keep W1's tested wire/auth adapters while the real framework owns tool invocation.</summary>
public sealed class PortModelClient(IChatModel model, IReadOnlyDictionary<ModelRole, string> deployments) : IChatClient
{
    /// <inheritdoc/>
    public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var role = options?.AdditionalProperties?["tcc.role"] is ModelRole chosen ? chosen : ModelRole.Narrator;
        if (!deployments.TryGetValue(role, out var deployment) || string.IsNullOrWhiteSpace(deployment))
        {
            throw new ModelException(ModelErrorKind.Configuration, "missing_role_model");
        }
        var tools = options?.Tools?.OfType<AIFunction>().Select(tool => new ToolSpec(tool.Name, tool.Description, tool.JsonSchema)).ToArray();
        var temperature = deployment.StartsWith("gpt-5", StringComparison.OrdinalIgnoreCase) ? null : options?.Temperature;
        var request = new ChatRequest(deployment, ConvertMessages(messages, options), temperature, tools);
        var content = new List<AIContent>();
        var prose = new StringBuilder();
        UsageDetails? usage = null;
        string? actualModel = null;
        await foreach (var item in model.StreamAsync(request, cancellationToken).ConfigureAwait(false))
        {
            switch (item)
            {
                case TextDelta delta: prose.Append(delta.Text); break;
                case ToolCall call:
                    Dictionary<string, object?> args;
                    try { args = JsonSerializer.Deserialize<Dictionary<string, object?>>(call.Arguments) ?? []; }
                    catch (JsonException) { throw new ModelException(ModelErrorKind.Unavailable, "malformed_tool_arguments"); }
                    content.Add(new FunctionCallContent(call.Id, call.Name, args));
                    break;
                case TaxCredit.Application.Ports.Ai.ModelUsage counted:
                    usage = new UsageDetails { InputTokenCount = counted.InputTokens, OutputTokenCount = counted.OutputTokens };
                    break;
                case StreamEnd end: actualModel = end.Model; break;
            }
        }
        if (prose.Length != 0) { content.Add(new TextContent(prose.ToString())); }
        return new ChatResponse(new ChatMessage(ChatRole.Assistant, content)) { Usage = usage, ModelId = actualModel };
    }

    private static List<TaxCredit.Application.Ports.Ai.ChatMessage> ConvertMessages(IEnumerable<ChatMessage> messages, ChatOptions? options)
    {
        var converted = new List<TaxCredit.Application.Ports.Ai.ChatMessage>();
        if (!string.IsNullOrEmpty(options?.Instructions)) { converted.Add(new("system", options.Instructions)); }
        foreach (var message in messages)
        {
            var calls = message.Contents.OfType<FunctionCallContent>()
                .Select(call => new ToolCall(call.CallId, call.Name, JsonSerializer.Serialize(call.Arguments))).ToArray();
            var results = message.Contents.OfType<FunctionResultContent>().ToArray();
            if (results.Length == 0)
            {
                converted.Add(new(message.Role.Value, message.Text, ToolCalls: calls.Length == 0 ? null : calls));
            }
            else
            {
                foreach (var result in results)
                {
                    converted.Add(new("tool", JsonSerializer.Serialize(result.Result), result.CallId));
                }
            }
        }
        return converted;
    }

    /// <inheritdoc/>
    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("The channel emits a completely guarded answer.");
    /// <inheritdoc/>
    public object? GetService(Type serviceType, object? serviceKey = null) => serviceType == typeof(IChatModel) ? model : null;
    /// <inheritdoc/>
    public void Dispose() { }
}
