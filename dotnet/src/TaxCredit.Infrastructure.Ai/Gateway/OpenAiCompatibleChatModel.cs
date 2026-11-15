using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Gateway;

/// <summary>An injected HTTP client is the sole transport; no SDK, tool execution, or model discovery occurs.</summary>
public sealed class OpenAiCompatibleChatModel(HttpClient http, GatewaySettings settings,
    IRequestAuthenticator auth, TimeProvider? clock = null) : IChatModel
{
    private const int MaxPayload = 1_048_576;
    /// <inheritdoc/>
    public string Name => settings.Name;
    /// <inheritdoc/>
    public ProviderStatus Status() => new(Name, ProviderState.Ready);
    /// <inheritdoc/>
    public async IAsyncEnumerable<ModelEvent> StreamAsync(ChatRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var message = await MessageAsync(request, cancellationToken).ConfigureAwait(false);
        using var response = await SendAsync(message, cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            if ((int)response.StatusCode == 401)
            {
                auth.Invalidate();
            }

            throw OpenAiWire.Error(response.StatusCode,
                response.Headers.TryGetValues("Retry-After", out var values) ? values.FirstOrDefault() : null,
                (clock ?? TimeProvider.System).GetUtcNow());
        }
        using var stream = await BoundedResponseReader.OpenAsync(response.Content, cancellationToken).ConfigureAwait(false);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        var decoder = new ChunkDecoder();
        if (!settings.Streaming)
        {
            string json = await BoundedResponseReader.WholeAsync(reader, cancellationToken).ConfigureAwait(false);
            foreach (var item in Decode(json, decoder, false))
            {
                yield return item;
            }
        }
        else
        {
            bool done = false;
            while (await BoundedResponseReader.LineAsync(reader, cancellationToken).ConfigureAwait(false) is { } line)
            {
                if (line.Length > MaxPayload)
                {
                    throw new ModelException(ModelErrorKind.Unavailable, "event_too_large");
                }

                if (!line.StartsWith("data:", StringComparison.Ordinal))
                {
                    continue;
                }

                string data = line[5..].Trim();
                if (data == "[DONE]") { done = true; break; }
                foreach (var item in Decode(data, decoder, true))
                {
                    yield return item;
                }
            }
            if (!done && decoder.FinishReason is null)
            {
                throw new ModelException(ModelErrorKind.Unavailable, "stream_truncated");
            }

            foreach (var call in decoder.Drain())
            {
                yield return call;
            }
        }
        yield return new StreamEnd(Name, request.Model, FinishReason: decoder.FinishReason);
    }
    private async Task<HttpRequestMessage> MessageAsync(ChatRequest request, CancellationToken ct)
    {
        var message = new HttpRequestMessage(HttpMethod.Post, OpenAiWire.BuildUri(settings, request.Model));
        try
        {
            var headers = new Dictionary<string, string>(settings.ExtraHeaders, StringComparer.OrdinalIgnoreCase)
            {
                ["Accept"] = settings.Streaming ? "text/event-stream" : "application/json",
                ["User-Agent"] = "tax-credit-copilot/1",
                ["X-Request-Id"] = Guid.NewGuid().ToString("N")
            };
            foreach (var pair in await auth.HeadersAsync(ct).ConfigureAwait(false))
            {
                headers[pair.Key] = pair.Value;
            }

            foreach (var pair in headers)
            {
                message.Headers.TryAddWithoutValidation(pair.Key, pair.Value);
            }

            message.Content = new StringContent(OpenAiWire.BuildBody(settings, request), Encoding.UTF8, "application/json");
            return message;
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { message.Dispose(); throw; }
        catch (ModelException) { message.Dispose(); throw; }
        catch (Exception)
        {
            message.Dispose();
            throw new ModelException(ModelErrorKind.BadRequest, "request_preparation_failed");
        }
    }
    private async Task<HttpResponseMessage> SendAsync(HttpRequestMessage message, CancellationToken ct)
    {
        try { return await http.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (OperationCanceledException) { throw new ModelException(ModelErrorKind.Timeout, "http_timeout"); }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "http_transport_failed"); }
    }
    private static IReadOnlyList<ModelEvent> Decode(string json, ChunkDecoder decoder, bool streaming)
    {
        if (json.Length > MaxPayload)
        {
            throw new ModelException(ModelErrorKind.Unavailable, "event_too_large");
        }

        try
        {
            using var doc = JsonDocument.Parse(json);
            return decoder.Decode(doc.RootElement, streaming);
        }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "malformed_model_event"); }
    }
}
