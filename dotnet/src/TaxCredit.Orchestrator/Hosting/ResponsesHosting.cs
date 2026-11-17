using Azure.AI.AgentServer.Core;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>One text handler; protocol routing, lifecycle and readiness belong to the installed SDK.</summary>
public static class ResponsesHosting
{
    /// <summary>Builds the real SDK host; the callback permits local scripted transports without Azure access.</summary>
    public static WebApplication Build(string[] args, IResponseTurn turn,
        Action<AgentHostBuilder>? configure = null)
    {
        var builder = AgentHost.CreateBuilder(args);
        if (string.IsNullOrWhiteSpace(builder.Configuration["urls"]))
        {
            builder.WebApplicationBuilder.WebHost.UseUrls("http://0.0.0.0:8088");
        }
        builder.Services.AddHttpContextAccessor();
        builder.Services.AddSingleton(turn);
        builder.AddResponses(provider => new ChannelResponseHandler(
            provider.GetRequiredService<IResponseTurn>(), provider.GetRequiredService<IHttpContextAccessor>()));
        configure?.Invoke(builder);
        return builder.Build().App;
    }

    private sealed class ChannelResponseHandler(IResponseTurn turn, IHttpContextAccessor http) : ResponseHandler
    {
        public override IAsyncEnumerable<ResponseStreamEvent> CreateAsync(CreateResponse request,
            ResponseContext context, CancellationToken cancellationToken) =>
            new TextResponse(context, request, createText: async ct =>
            {
                using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, context.Shutdown,
                    context.ClientCancellation, cancellationToken);
                var input = await context.GetInputTextAsync(cancellationToken: linked.Token).ConfigureAwait(false);
                var headers = http.HttpContext?.Request.Headers.ToDictionary(pair => pair.Key,
                    pair => pair.Value.ToString(), StringComparer.OrdinalIgnoreCase) ?? [];
                var conversation = Conversation(request);
                return await turn.AnswerAsync(new ResponseTurnRequest(input, headers, conversation,
                    context.ConversationChainId, context.ResponseId, context.PlatformContext.UserIdKey),
                    linked.Token).ConfigureAwait(false);
            });
    }

    private static string? Conversation(CreateResponse request)
    {
        if (request.Conversation is not { } conversation)
        {
            return null;
        }
        using var document = System.Text.Json.JsonDocument.Parse(conversation.ToString());
        var root = document.RootElement;
        return root.ValueKind == System.Text.Json.JsonValueKind.String ? root.GetString() :
            root.TryGetProperty("id", out var id) ? id.GetString() : null;
    }
}

/// <summary>SDK-independent request context keeps deterministic decisions testable without a server.</summary>
public sealed record ResponseTurnRequest(string Text, IReadOnlyDictionary<string, string> Headers,
    string? ConversationId, string? ConversationChainId, string ResponseId, string? AgentUserId);

/// <summary>The host can return only the shared turn pipeline's fully composed text.</summary>
public interface IResponseTurn
{
    /// <summary>Identity, tools and guarded composition are completed before the SDK emits text.</summary>
    Task<string> AnswerAsync(ResponseTurnRequest request, CancellationToken cancellationToken);
}
