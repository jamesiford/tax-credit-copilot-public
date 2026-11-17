using System.Net;
using System.Text;
using System.Text.Json;

namespace TaxCredit.Deployment.Telemetry;

internal sealed class Transport : IDisposable
{
    private readonly HttpClient _client = new(new SocketsHttpHandler
    {
        ConnectTimeout = TimeSpan.FromMilliseconds(500),
        AllowAutoRedirect = false,
        UseProxy = false,
        ActivityHeadersPropagator = null
    })
    { Timeout = TimeSpan.FromMilliseconds(750), MaxResponseContentBufferSize = 4096 };

    public void Dispose() => _client.Dispose();

    internal void Send(Uri endpoint, string path, object payload)
    {
        try
        {
            using var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            using var response = _client.PostAsync(new Uri(endpoint, path), content).GetAwaiter().GetResult();
            if (response.StatusCode != HttpStatusCode.OK)
            {
                Diagnostics.ExportFailed();
                return;
            }
            var body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            if (Rejected(body)) { Diagnostics.ExportFailed(); }
        }
        catch (Exception error) when (error is HttpRequestException or OperationCanceledException or JsonException)
        {
            Diagnostics.ExportFailed();
        }
    }

    private static bool Rejected(string body)
    {
        using var document = JsonDocument.Parse(body);
        if (document.RootElement.ValueKind != JsonValueKind.Object) { return true; }
        if (!document.RootElement.TryGetProperty("partialSuccess", out var partial)) { return false; }
        if (partial.ValueKind != JsonValueKind.Object) { return true; }
        foreach (var field in partial.EnumerateObject())
        {
            if (field.Name is "rejectedSpans" or "rejectedDataPoints" or "errorMessage"
                && field.Value.ToString() is not ("" or "0"))
            {
                return true;
            }
        }
        return false;
    }
}
