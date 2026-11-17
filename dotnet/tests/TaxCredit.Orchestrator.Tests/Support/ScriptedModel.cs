using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Tests.Support;

internal sealed class ScriptedModel(params Func<ChatResponse>[] script) : IChatClient
{
    private readonly Queue<Func<ChatResponse>> _script = new(script);
    internal List<(ChatMessage[] Messages, ChatOptions? Options)> Seen { get; } = [];

    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Seen.Add((messages.ToArray(), options));
        if (_script.Count == 0) { throw new ModelException(ModelErrorKind.Unavailable, "script_exhausted"); }
        return Task.FromResult(_script.Dequeue()());
    }

    internal static Func<ChatResponse> Text(string text) => () => new ChatResponse(new ChatMessage(ChatRole.Assistant, text)) { ModelId = "test-model" };
    internal static Func<ChatResponse> Error() => () => throw new ModelException(ModelErrorKind.BadRequest, "scripted_failure");
    internal static Func<ChatResponse> Tools(params (string Name, JsonObject Args)[] calls) => () =>
        new ChatResponse(new ChatMessage(ChatRole.Assistant, calls.Select((call, index) => (AIContent)new FunctionCallContent(
            "call-" + index, call.Name, call.Args.ToDictionary(pair => pair.Key,
                pair => (object?)JsonSerializer.SerializeToElement(pair.Value)))).ToList()))
        { ModelId = "test-model" };

    internal IEnumerable<string> VisibleRequests() => Seen.Select(request => string.Join("\n", request.Messages
        .SelectMany(message => message.Contents).Select(content => content switch
        {
            TextContent text => text.Text,
            FunctionResultContent result => JsonSerializer.Serialize(result.Result),
            FunctionCallContent call => JsonSerializer.Serialize(call.Arguments),
            _ => "",
        })));

    public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
    public object? GetService(Type serviceType, object? serviceKey = null) => null;
    public void Dispose() { }
}
