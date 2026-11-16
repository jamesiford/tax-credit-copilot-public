using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.Ai;

/// <summary>Optional AI handlers join the mediator only when their feature dependencies are registered.</summary>
public static class AiHandlerRegistration
{
    /// <summary>Keeps capability composition usable independently of prompt and stream services.</summary>
    public static IServiceCollection AddAiCapabilityHandlers(this IServiceCollection services)
    {
        services.TryAddScoped<ListCapabilitiesHandler>();
        services.TryAddScoped<InvokeCapabilityHandler>();
        services.TryAddScoped<IRequestHandler<ListCapabilitiesQuery, JsonObject>, ListRequest>();
        services.TryAddScoped<IRequestHandler<InvokeCapabilityQuery, JsonObject>, InvokeRequest>();
        return services;
    }

    /// <summary>A bare application/runtime container must not discover handlers for an absent optional feature.</summary>
    public static IServiceCollection AddAiStreamHandlers(this IServiceCollection services)
    {
        services.TryAddScoped<ChatHandler>();
        services.TryAddScoped<SummaryHandler>();
        services.TryAddScoped<IRequestHandler<ChatQuery, IAsyncEnumerable<AiFrame>>, ChatRequest>();
        services.TryAddScoped<IRequestHandler<SummaryQuery, IAsyncEnumerable<AiFrame>>, SummaryRequest>();
        return services;
    }

    private sealed class ListRequest(ListCapabilitiesHandler handler) : IRequestHandler<ListCapabilitiesQuery, JsonObject>
    {
        public ValueTask<JsonObject> Handle(ListCapabilitiesQuery request, CancellationToken cancellationToken) =>
            handler.Handle(request, cancellationToken);
    }

    private sealed class InvokeRequest(InvokeCapabilityHandler handler) : IRequestHandler<InvokeCapabilityQuery, JsonObject>
    {
        public ValueTask<JsonObject> Handle(InvokeCapabilityQuery request, CancellationToken cancellationToken) =>
            handler.Handle(request, cancellationToken);
    }

    private sealed class ChatRequest(ChatHandler handler) : IRequestHandler<ChatQuery, IAsyncEnumerable<AiFrame>>
    {
        public ValueTask<IAsyncEnumerable<AiFrame>> Handle(ChatQuery request, CancellationToken cancellationToken) =>
            handler.Handle(request, cancellationToken);
    }

    private sealed class SummaryRequest(SummaryHandler handler) : IRequestHandler<SummaryQuery, IAsyncEnumerable<AiFrame>>
    {
        public ValueTask<IAsyncEnumerable<AiFrame>> Handle(SummaryQuery request, CancellationToken cancellationToken) =>
            handler.Handle(request, cancellationToken);
    }
}
