using System.Runtime.CompilerServices;
using System.Text.Json;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.Ai;

/// <summary>Both operations stream application events through the shared flushing transport.</summary>
public sealed class ChatSummaryEndpoints : IEndpointGroup
{
    private static readonly JsonSerializerOptions Input = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        endpoints.MapPost("/api/chat", async (HttpContext http, [FromKeyedServices(AiFeatureModule.MediatorKey)] IMediator mediator) =>
        {
            var query = RequestValidator.Body(http)!.Value.Deserialize<ChatQuery>(Input)!;
            var frames = await mediator.Send(query, http.RequestAborted).ConfigureAwait(false);
            return new EventStream(Transport(frames, http.RequestAborted));
        });
        endpoints.MapPost("/api/summary", async (HttpContext http, [FromKeyedServices(AiFeatureModule.MediatorKey)] IMediator mediator) =>
        {
            var query = RequestValidator.Body(http)!.Value.Deserialize<SummaryQuery>(Input)!;
            var frames = await mediator.Send(query, http.RequestAborted).ConfigureAwait(false);
            return new EventStream(Transport(frames, http.RequestAborted));
        });
    }

    private static async IAsyncEnumerable<StreamEvent> Transport(IAsyncEnumerable<AiFrame> frames,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        await foreach (var frame in frames.WithCancellation(cancellationToken).ConfigureAwait(false))
        {
            yield return new(frame.Event, frame.Data);
        }
    }
}
