using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Gateway;

/// <summary>The model is carried in a body or an Azure deployment path.</summary>
public enum GatewayDialect
{
    /// <summary>OpenAI v1 chat-completions.</summary>
    OpenAiV1,
    /// <summary>Azure deployment-scoped completions.</summary>
    AzureDeployments
}

/// <summary>Immutable nonsecret gateway settings; diagnostics redact endpoint and headers.</summary>
public sealed class GatewaySettings
{
    /// <summary>Validates HTTPS and header syntax before any transport can run.</summary>
    public GatewaySettings(Uri endpoint, GatewayDialect dialect = GatewayDialect.OpenAiV1,
        string apiVersion = "2024-10-21", bool streaming = true,
        IReadOnlyDictionary<string, string>? extraHeaders = null, string name = "gateway")
    {
        if (!endpoint.IsAbsoluteUri || endpoint.Scheme != "https" || !string.IsNullOrEmpty(endpoint.UserInfo)
            || !string.IsNullOrEmpty(endpoint.Query) || !string.IsNullOrEmpty(endpoint.Fragment)
            || string.IsNullOrWhiteSpace(apiVersion) || string.IsNullOrWhiteSpace(name))
        {
            throw new ModelException(ModelErrorKind.Configuration, "invalid_gateway_settings");
        }

        Endpoint = endpoint;
        Dialect = dialect;
        ApiVersion = apiVersion;
        Streaming = streaming;
        Name = name;
        ExtraHeaders = extraHeaders ?? new Dictionary<string, string>();
        if (ExtraHeaders.Any(p => p.Key.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-')
            || p.Value.Any(c => c is '\r' or '\n')))
        {
            throw new ModelException(ModelErrorKind.Configuration, "invalid_gateway_headers");
        }
    }
    /// <summary>The configured HTTPS service root.</summary>
    public Uri Endpoint { get; }
    /// <summary>The explicit wire dialect.</summary>
    public GatewayDialect Dialect { get; }
    /// <summary>The Azure API version.</summary>
    public string ApiVersion { get; }
    /// <summary>Whether to request streamed events.</summary>
    public bool Streaming { get; }
    /// <summary>The registered provider label.</summary>
    public string Name { get; }
    /// <summary>Extra request headers, overridden by authentication.</summary>
    public IReadOnlyDictionary<string, string> ExtraHeaders { get; }
    /// <inheritdoc/>
    public override string ToString() => "GatewaySettings(endpoint=<redacted>, headers=<redacted>)";
}
