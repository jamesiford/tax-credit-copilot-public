namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Separate transport observations distinguish DNS, private routing, TLS and client/proxy failures.</summary>
public interface IDiagnosticNetworkProbe
{
    /// <summary>Resolve addresses without requiring or returning any credential.</summary>
    Task<IReadOnlyList<string>> ResolveAsync(string host, CancellationToken cancellationToken);
    /// <summary>Connect to the selected address on TLS port 443.</summary>
    Task ConnectAsync(string address, CancellationToken cancellationToken);
    /// <summary>Perform an unauthenticated TLS GET and return only the status, never the body or headers.</summary>
    Task<int> TlsGetStatusAsync(string host, string address, CancellationToken cancellationToken);
    /// <summary>Separately exercise the application's HTTP transport and proxy configuration, without authentication.</summary>
    Task<int> HttpGetStatusAsync(Uri uri, CancellationToken cancellationToken);
}

/// <summary>The model adapter returns metadata only, making generated reply text unavailable to diagnostics.</summary>
public sealed record ModelProbeObservation(Uri? BaseUri, int ReplyCharacters);

/// <summary>An explicitly injected SDK probe owns its model call, credentials and client lifetime.</summary>
public delegate Task<ModelProbeObservation> ModelDiagnosticCall(Uri endpoint, string model, CancellationToken cancellationToken);

/// <summary>Diagnostic configuration snapshots only safe metadata, not arbitrary environment values.</summary>
public sealed record DiagnosticOptions
{
    /// <summary>Configured project endpoint, absent if invalid or credential-bearing.</summary>
    public Uri? ProjectEndpoint { get; }
    /// <summary>Configured gateway endpoint, absent if invalid or credential-bearing.</summary>
    public Uri? GatewayEndpoint { get; }
    /// <summary>The selected model deployment, not generated model text.</summary>
    public string Model { get; }
    /// <summary>Configured provider identifiers.</summary>
    public IReadOnlyList<string> Providers { get; }
    /// <summary>Per-operation budget, including collaborators which fail to observe cancellation.</summary>
    public TimeSpan StepTimeout { get; }
    /// <summary>Bounds the complete command, not just each individual network operation.</summary>
    public TimeSpan TotalTimeout { get; }
    internal System.Text.Json.Nodes.JsonObject Environment { get; }

    /// <summary>Explicit endpoints/providers override environment configuration without retaining environment secrets.</summary>
    public DiagnosticOptions(IReadOnlyDictionary<string, string?> environment, string? projectEndpoint = null,
        string? gatewayUrl = null, IEnumerable<string>? providers = null, TimeSpan? stepTimeout = null, TimeSpan? totalTimeout = null)
    {
        ArgumentNullException.ThrowIfNull(environment);
        string Text(string name) => environment.TryGetValue(name, out var value) ? value?.Trim() ?? "" : "";
        ProjectEndpoint = DiagnosticMetadata.SafeEndpoint(projectEndpoint ?? Text("FOUNDRY_PROJECT_ENDPOINT"));
        GatewayEndpoint = DiagnosticMetadata.SafeEndpoint(gatewayUrl ?? Text("CHANNEL_GATEWAY_URL"));
        Model = Text("FOUNDRY_MODEL") is { Length: > 0 } selected ? selected : Text("AZURE_AI_MODEL_DEPLOYMENT_NAME");
        if (Model.Length > 256 || Model.Any(char.IsControl))
        {
            throw new ArgumentException("Diagnostic model names must be bounded metadata.", nameof(environment));
        }
        Providers = Array.AsReadOnly((providers ?? Text("AI_PROVIDER_CHAIN").Split(','))
            .Select(provider => provider.Trim()).Where(provider => provider.Length is > 0 and <= 100 && !provider.Any(char.IsControl))
            .Take(8).ToArray());
        StepTimeout = Budget(stepTimeout ?? TimeSpan.FromSeconds(10), nameof(stepTimeout), 30);
        TotalTimeout = Budget(totalTimeout ?? TimeSpan.FromSeconds(90), nameof(totalTimeout), 300);
        Environment = DiagnosticMetadata.EnvironmentReport(environment);
    }

    private static TimeSpan Budget(TimeSpan value, string name, int maximum) =>
        value > TimeSpan.Zero && value <= TimeSpan.FromSeconds(maximum) ? value : throw new ArgumentOutOfRangeException(name);
}
