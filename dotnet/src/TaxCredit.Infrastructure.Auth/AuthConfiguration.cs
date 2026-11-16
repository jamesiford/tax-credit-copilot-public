namespace TaxCredit.Infrastructure.Auth;

/// <summary>Explicit anonymous opt-in prevents accidental deployment over private data.</summary>
public sealed record AuthConfiguration
{
    /// <summary>Configuration diagnostics must not disclose directory/registration identifiers.</summary>
    public override string ToString() => "AuthConfiguration";
    /// <summary>Authentication defaults to Entra.</summary>
    public string Mode { get; init; } = "entra";
    /// <summary>Exactly one directory is trusted.</summary>
    public string TenantId { get; init; } = "";
    /// <summary>API audience; api:// forms also accept their bare registration id.</summary>
    public string ApiAudience { get; init; } = "";
    /// <summary>Only explicit local enables anonymous development.</summary>
    public string? Environment { get; init; }
    /// <summary>Synthetic classification is required for deployed anonymous demos.</summary>
    public string? DataClassification { get; init; }
    /// <summary>A demo must opt in separately.</summary>
    public bool AllowAnonymousSynthetic { get; init; }
    /// <summary>Existing portal users remain writable unless explicitly enforced.</summary>
    public bool EnforceWriterForUsers { get; init; }
    /// <summary>Fail startup rather than granting anonymous fallback.</summary>
    public void Validate()
    {
        var mode = Mode.Trim().ToLowerInvariant();
        if (mode is "" or "entra")
        {
            if (!Guid.TryParse(TenantId, out _) || string.IsNullOrWhiteSpace(ApiAudience))
            {
                throw new ArgumentException("Entra needs AUTH_TENANT_ID and API_AUDIENCE.");
            }

            return;
        }
        if (mode != "none")
        {
            throw new ArgumentException("Unknown AUTH_MODE.");
        }

        if (string.Equals(Environment?.Trim(), "local", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (!AllowAnonymousSynthetic || !string.Equals(DataClassification?.Trim(), "synthetic", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("AUTH_MODE=none is only for explicit local development or a flagged synthetic demo.");
        }
    }
    /// <summary>The v2 issuer is deliberately not the v1 STS issuer.</summary>
    public string Issuer => $"https://login.microsoftonline.com/{TenantId}/v2.0";
    /// <summary>Keys are fetched from the configured tenant, never a token-controlled URL.</summary>
    public Uri JwksUri => new($"https://login.microsoftonline.com/{TenantId}/discovery/v2.0/keys");
    /// <summary>API alternatives are registration forms, not gateway audiences.</summary>
    public IReadOnlyList<string> Audiences => ApiAudience.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
        .SelectMany(a => a.StartsWith("api://", StringComparison.Ordinal) ? new[] { a, a[6..] } : [a])
        .Distinct(StringComparer.Ordinal).ToArray();
}
