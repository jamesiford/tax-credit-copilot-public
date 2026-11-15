using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Options;

namespace TaxCredit.Api.Wire;

/// <summary>Flushes each named JSON frame; buffering would turn token streaming into a delayed response.</summary>
public sealed class EventStream(IAsyncEnumerable<StreamEvent> events) : IResult
{
    /// <inheritdoc />
    public async Task ExecuteAsync(HttpContext httpContext)
    {
        ArgumentNullException.ThrowIfNull(httpContext);
        httpContext.Response.ContentType = "text/event-stream";
        httpContext.Response.Headers.CacheControl = "no-cache";
        httpContext.Response.Headers["X-Accel-Buffering"] = "no";
        httpContext.Features.Get<IHttpResponseBodyFeature>()?.DisableBuffering();
        var options = httpContext.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value.SerializerOptions;
        await foreach (var frame in events.WithCancellation(httpContext.RequestAborted).ConfigureAwait(false))
        {
            if (frame.Event.Length == 0 || frame.Event.Contains('\n') || frame.Event.Contains('\r'))
            {
                throw new InvalidOperationException("An event name must be a nonempty single line.");
            }

            await httpContext.Response.WriteAsync($"event: {frame.Event}\ndata: {JsonSerializer.Serialize(frame.Data, options)}\n\n", httpContext.RequestAborted).ConfigureAwait(false);
            await httpContext.Response.Body.FlushAsync(httpContext.RequestAborted).ConfigureAwait(false);
        }
    }
}

/// <summary>A named event with a canonical tool brief or a narration token.</summary>
/// <param name="Event">The client's event discriminator.</param>
/// <param name="Data">The JSON payload.</param>
public sealed record StreamEvent(string Event, object? Data);
