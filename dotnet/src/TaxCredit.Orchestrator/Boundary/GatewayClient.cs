using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Stateless REST infrastructure never retains a caller's identity or authentication token.</summary>
public sealed class GatewayClient : IGatewayClient
{
    private readonly HttpClient http;
    private readonly IServiceTokenProvider tokens;
    private readonly GatewaySettings settings;

    /// <summary>The owner manages HttpClient lifetime and must disable redirects and automatic mutation retries.</summary>
    public GatewayClient(HttpClient http, IServiceTokenProvider tokens, GatewaySettings settings)
    {
        ArgumentNullException.ThrowIfNull(http);
        ArgumentNullException.ThrowIfNull(tokens);
        ArgumentNullException.ThrowIfNull(settings);
        this.http = http;
        this.tokens = tokens;
        this.settings = settings;
    }

    /// <summary>Default composition disables redirects so acting assertions cannot cross gateway origins.</summary>
    public static HttpClient CreateHttpClient() => new(new SocketsHttpHandler
    {
        AllowAutoRedirect = false,
        UseCookies = false,
        ConnectTimeout = TimeSpan.FromSeconds(10),
    })
    {
        Timeout = Timeout.InfiniteTimeSpan,
    };

    /// <inheritdoc />
    public Task<GatewayReply> CallToolAsync(ActingIdentity identity, string tool, JsonObject arguments,
        string? idempotencyKey = null, string? confirmationToken = null, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(tool);
        ArgumentNullException.ThrowIfNull(arguments);
        if (tool.Length > 128 || tool.Any(character => !char.IsAsciiLetterOrDigit(character) && character != '_'))
        {
            throw new ArgumentException("Tool names must be catalogue identifiers.", nameof(tool));
        }
        var body = new JsonObject { ["args"] = arguments.DeepClone() };
        if (!string.IsNullOrEmpty(idempotencyKey))
        {
            body["idempotency_key"] = idempotencyKey;
        }
        if (!string.IsNullOrEmpty(confirmationToken))
        {
            body["confirmation_token"] = confirmationToken;
        }
        return PostAsync("channel/v1/tools/" + tool, identity, body, cancellationToken);
    }

    /// <inheritdoc />
    public Task<GatewayReply> ReportNarrationAsync(ActingIdentity identity, JsonObject report, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(report);
        return PostAsync("channel/v1/audit/narration", identity, report, cancellationToken);
    }

    private async Task<GatewayReply> PostAsync(string path, ActingIdentity identity, JsonObject body, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(identity);
        cancellationToken.ThrowIfCancellationRequested();
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(settings.RequestTimeout);
        try
        {
            var token = await tokens.GetTokenAsync(budget.Token).AsTask().WaitAsync(budget.Token).ConfigureAwait(false);
            if (string.IsNullOrWhiteSpace(token))
            {
                return GatewayReply.Failure("gateway_unreachable");
            }
            using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(settings.BaseUri, path));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            foreach (var (name, value) in identity.GatewayHeaders())
            {
                request.Headers.Add(name, value);
            }
            request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, budget.Token).ConfigureAwait(false);
            return await ReadReplyAsync(response, budget.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return GatewayReply.Failure("timeout");
        }
#pragma warning disable CA1031 // This dependency boundary deliberately returns no credential/transport exception detail.
        catch (Exception exception) when (exception is not (OperationCanceledException or OutOfMemoryException))
        {
            return GatewayReply.Failure("gateway_unreachable");
        }
#pragma warning restore CA1031
    }

    private async Task<GatewayReply> ReadReplyAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var status = (int)response.StatusCode;
        if (response.Content.Headers.ContentLength > settings.MaxResponseBytes)
        {
            return GatewayReply.Failure("response_too_large", "the gateway response exceeded the size limit", status);
        }
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using var output = new MemoryStream();
        var buffer = new byte[Math.Min(settings.MaxResponseBytes + 1, 8192)];
        while (true)
        {
            var read = await stream.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                break;
            }
            if (output.Length + read > settings.MaxResponseBytes)
            {
                return GatewayReply.Failure("response_too_large", "the gateway response exceeded the size limit", status);
            }
            output.Write(buffer, 0, read);
        }
        try
        {
            var parsed = JsonNode.Parse(output.GetBuffer().AsSpan(0, checked((int)output.Length)));
            return new GatewayReply(status, parsed as JsonObject ?? new JsonObject { ["detail"] = parsed });
        }
        catch (JsonException)
        {
            return GatewayReply.Failure("bad_response", "the gateway did not return JSON", status);
        }
    }
}
