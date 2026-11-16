using System.Globalization;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>One fixed gateway destination and bounded transport budgets, separate from planner settings.</summary>
public sealed record GatewaySettings
{
    /// <summary>The only origin to which service credentials and reader assertions may be sent.</summary>
    public Uri BaseUri { get; }
    /// <summary>The gateway application audience, not the backend API's audience.</summary>
    public string Audience { get; }
    /// <summary>Azure credentials are requested with the application default scope on every call.</summary>
    public string Scope => Audience.TrimEnd('/') + "/.default";
    /// <summary>Bounds token acquisition, HTTP headers and reading the complete response.</summary>
    public TimeSpan RequestTimeout { get; }
    /// <summary>Prevents an unbounded upstream response from exhausting the hosted process.</summary>
    public int MaxResponseBytes { get; }

    /// <summary>Reject insecure or ambiguous destinations at startup, without contacting them.</summary>
    public GatewaySettings(Uri baseUri, string audience, TimeSpan? requestTimeout = null, int maxResponseBytes = 4 * 1024 * 1024)
    {
        ArgumentNullException.ThrowIfNull(baseUri);
        ArgumentException.ThrowIfNullOrWhiteSpace(audience);
        if (!baseUri.IsAbsoluteUri || baseUri.Scheme != Uri.UriSchemeHttps || baseUri.UserInfo.Length != 0 ||
            baseUri.Query.Length != 0 || baseUri.Fragment.Length != 0)
        {
            throw new ArgumentException("CHANNEL_GATEWAY_URL must be an absolute HTTPS URL without credentials, query or fragment.", nameof(baseUri));
        }
        var timeout = requestTimeout ?? TimeSpan.FromSeconds(40);
        if (timeout <= TimeSpan.Zero || timeout > TimeSpan.FromSeconds(300))
        {
            throw new ArgumentOutOfRangeException(nameof(requestTimeout));
        }
        if (maxResponseBytes is < 1 or > 64 * 1024 * 1024)
        {
            throw new ArgumentOutOfRangeException(nameof(maxResponseBytes));
        }
        BaseUri = new Uri(baseUri.AbsoluteUri.TrimEnd('/') + "/", UriKind.Absolute);
        Audience = audience.Trim();
        RequestTimeout = timeout;
        MaxResponseBytes = maxResponseBytes;
    }

    /// <summary>Read the existing channel gateway environment variables without model configuration.</summary>
    public static GatewaySettings FromEnvironment(IReadOnlyDictionary<string, string?> environment)
    {
        ArgumentNullException.ThrowIfNull(environment);
        string Text(string key) => environment.TryGetValue(key, out var value) ? value?.Trim() ?? "" : "";
        var timeout = Text("CHANNEL_REQUEST_TIMEOUT_SECONDS");
        var seconds = timeout.Length == 0 ? 40 : int.Parse(timeout, CultureInfo.InvariantCulture);
        if (seconds is < 5 or > 300)
        {
            throw new ArgumentOutOfRangeException(nameof(environment), "CHANNEL_REQUEST_TIMEOUT_SECONDS must be between 5 and 300.");
        }
        return new GatewaySettings(new Uri(Text("CHANNEL_GATEWAY_URL"), UriKind.Absolute),
            Text("CHANNEL_GATEWAY_AUDIENCE"), TimeSpan.FromSeconds(seconds));
    }
}
