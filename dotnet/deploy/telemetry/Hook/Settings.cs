using System.Text.RegularExpressions;

namespace TaxCredit.Deployment.Telemetry;

internal sealed partial record Settings(Uri Endpoint, string Service, string Version)
{
    internal static Settings? Read()
    {
        var enabled = Environment.GetEnvironmentVariable("TCC_TELEMETRY_ENABLED");
        if (enabled is null or "0")
        {
            return null;
        }
        if (enabled != "1")
        {
            Diagnostics.InvalidConfiguration();
            return null;
        }
        var service = Environment.GetEnvironmentVariable("OTEL_SERVICE_NAME");
        var version = Environment.GetEnvironmentVariable("TCC_TELEMETRY_VERSION");
        var address = Environment.GetEnvironmentVariable("TCC_TELEMETRY_ENDPOINT");
        if (service is not ("taxcredit-api" or "taxcredit-gateway" or "taxcredit-worker" or "taxcredit-orchestrator")
            || version is null || !VersionPattern().IsMatch(version)
            || !Uri.TryCreate(address, UriKind.Absolute, out var endpoint)
            || endpoint.Scheme is not ("http" or "https")
            || endpoint.UserInfo.Length != 0 || endpoint.Query.Length != 0
            || endpoint.Fragment.Length != 0 || endpoint.AbsolutePath != "/")
        {
            Diagnostics.InvalidConfiguration();
            return null;
        }
        // Plain HTTP is deliberately confined to a sidecar on loopback.
        if (endpoint.Scheme == "http" && !endpoint.IsLoopback)
        {
            Diagnostics.InvalidConfiguration();
            return null;
        }
        return new(endpoint, service, version);
    }

    [GeneratedRegex(@"\A(?:[0-9a-f]{7,40}|[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4})\z", RegexOptions.CultureInvariant)]
    private static partial Regex VersionPattern();
}
