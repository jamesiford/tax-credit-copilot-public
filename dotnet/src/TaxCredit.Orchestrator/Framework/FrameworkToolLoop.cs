using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>All planners enter the actual framework tool loop and the same function middleware.</summary>
public sealed class FrameworkToolLoop(ModelToolCatalog catalog)
{
    internal const string TurnKey = "tcc.turn";

    /// <summary>A bounded, sequential tool loop prevents parallel writes and shares one ledger.</summary>
    public async Task<string> RunAsync(IChatClient client, IToolExecution turn, string question,
        string instructions, int maxCalls, CancellationToken cancellationToken)
    {
        using var observed = new ObservedClient(client, turn, catalog);
        using var invoking = new FunctionInvokingChatClient(observed)
        {
            MaximumIterationsPerRequest = Math.Max(2, maxCalls + 1),
            AllowConcurrentInvocation = false,
            IncludeDetailedErrors = false,
        };
        var options = new ChatClientAgentOptions
        {
            Name = "tcc-channel-orchestrator",
            AllowConcurrentInvocation = false,
            UseProvidedChatClientAsIs = true,
            ChatOptions = new ChatOptions
            {
                Instructions = instructions,
                Tools = catalog.Definitions.ToList(),
                AdditionalProperties = new()
                {
                    [TurnKey] = turn,
                    ["tcc.role"] = TaxCredit.Application.Ports.Ai.ModelRole.Narrator,
                },
            },
        };
        var agent = new ChatClientAgent(invoking, options).AsBuilder()
            .Use(InvokeAsync).Build();
        var result = await agent.RunAsync(question, cancellationToken: cancellationToken).ConfigureAwait(false);
        return result.Text;
    }

    /// <summary>Degraded planners use a scripted SDK client, not a second implementation of the rules.</summary>
    public async Task RunOneAsync(IToolExecution turn, string name, JsonObject arguments, CancellationToken cancellationToken)
    {
        if (catalog.Find(name) is null)
        {
            turn.RefuseUnknown(name);
            return;
        }
        using var one = new OneCallClient(name, arguments);
        await RunAsync(one, turn, "call", "", 1, cancellationToken).ConfigureAwait(false);
    }

    private static async ValueTask<object?> InvokeAsync(AIAgent agent, FunctionInvocationContext context,
        Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
    {
        var turn = context.Options?.AdditionalProperties?[TurnKey] as IToolExecution
            ?? throw new InvalidOperationException("No attributed tool context.");
        var proposed = JsonSerializer.SerializeToNode(context.Arguments)!.AsObject();
        return await turn.InvokeAsync(context.Function.Name, proposed, async (settled, ct) =>
        {
            context.Arguments = new AIFunctionArguments(settled.ToDictionary(pair => pair.Key,
                pair => (object?)JsonSerializer.SerializeToElement(pair.Value)))
            {
                Context = new Dictionary<object, object?> { [TurnKey] = turn },
            };
            return await next(context, ct).ConfigureAwait(false);
        }, cancellationToken).ConfigureAwait(false);
    }

    private sealed class OneCallClient(string name, JsonObject arguments) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var completed = messages.Any(message => message.Contents.OfType<FunctionResultContent>().Any());
            return Task.FromResult(new ChatResponse(completed
                ? new ChatMessage(ChatRole.Assistant, "")
                : new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("one-call", name,
                    arguments.ToDictionary(pair => pair.Key, pair => (object?)JsonSerializer.SerializeToElement(pair.Value)))])));
        }

        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
            ChatOptions? options = null, CancellationToken cancellationToken = default) =>
            throw new NotSupportedException("The composed channel response is not streamed.");
        public object? GetService(Type serviceType, object? serviceKey = null) => null;
        public void Dispose() { }
    }

    private sealed class ObservedClient(IChatClient inner, IToolExecution turn, ModelToolCatalog tools) : DelegatingChatClient(inner)
    {
        public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages,
            ChatOptions? options = null, CancellationToken cancellationToken = default)
        {
            var response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
            foreach (var call in response.Messages.SelectMany(message => message.Contents).OfType<FunctionCallContent>())
            {
                if (tools.Find(call.Name) is null)
                {
                    turn.RefuseUnknown(call.Name);
                }
            }
            return response;
        }

        [System.Diagnostics.CodeAnalysis.SuppressMessage("Usage", "CA2215",
            Justification = "The process owns the injected model client; disposing a turn must not dispose a shared provider.")]
        protected override void Dispose(bool disposing) { }
    }
}
