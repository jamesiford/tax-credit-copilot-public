using System.Net;
using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Pure diagnostic projection never serializes arbitrary environment values, URI credentials or exception messages.</summary>
public static class DiagnosticMetadata
{
    private static readonly string[] SafeValues =
        ["FOUNDRY_MODEL", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "AI_PROVIDER_CHAIN", "CHANNEL_NAME", "CHANNEL_IDENTITY_SOURCES"];
    private static readonly string[] Prefixes = ["FOUNDRY_", "AI_", "AZURE_AI_", "CHANNEL_"];
    private static readonly string[] ProxyNames =
        ["HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy"];
    private static readonly IPNetwork[] PrivateNetworks = Networks(
        "0.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
        "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4",
        "::/128", "::1/128", "64:ff9b:1::/48", "100::/64", "2001::/23", "2001:db8::/32", "2002::/16",
        "3fff::/20", "fc00::/7", "fe80::/10");
    private static readonly IPNetwork[] PublicExceptions = Networks(
        "192.0.0.9/32", "192.0.0.10/32", "2001:1::1/128", "2001:1::2/128", "2001:3::/32",
        "2001:4:112::/48", "2001:20::/28", "2001:30::/28");

    /// <summary>Classify addresses like the CPython oracle, including reserved and IPv4-mapped addresses.</summary>
    public static string Classify(string address)
    {
        if (!IPAddress.TryParse(address, out var ip))
        {
            return "invalid";
        }
        ip = ip.IsIPv4MappedToIPv6 ? ip.MapToIPv4() : ip;
        if (IPAddress.IsLoopback(ip))
        {
            return "loopback";
        }
        var bytes = ip.GetAddressBytes();
        if (ip.IsIPv6LinkLocal || bytes.Length == 4 && bytes[0] == 169 && bytes[1] == 254)
        {
            return "link-local";
        }
        return PrivateNetworks.Any(network => network.Contains(ip)) && !PublicExceptions.Any(network => network.Contains(ip))
            ? "private" : "public";
    }

    /// <summary>Derive the three Foundry account targets, without accepting arbitrary endpoint credentials or queries.</summary>
    public static IReadOnlyList<DiagnosticTarget> AccountHosts(string? projectEndpoint)
    {
        var endpoint = SafeEndpoint(projectEndpoint);
        if (endpoint is null)
        {
            return [];
        }
        if (Uri.CheckHostName(endpoint.DnsSafeHost) != UriHostNameType.Dns)
        {
            return [new DiagnosticTarget(endpoint.DnsSafeHost, "/openai/v1/models")];
        }
        var account = endpoint.DnsSafeHost.Split('.')[0];
        return
        [
            new(endpoint.DnsSafeHost, "/openai/v1/models"),
            new(account + ".openai.azure.com", "/openai/models?api-version=2024-10-21"),
            new(account + ".cognitiveservices.azure.com"),
        ];
    }

    /// <summary>Names are diagnostic evidence; only the source's explicit five non-secret values may be shown.</summary>
    public static JsonObject EnvironmentReport(IReadOnlyDictionary<string, string?> environment)
    {
        ArgumentNullException.ThrowIfNull(environment);
        var names = environment.Keys.Where(name => name.Length <= 128 &&
            name.All(character => char.IsAsciiLetterOrDigit(character) || character == '_') &&
            Prefixes.Any(prefix => name.StartsWith(prefix, StringComparison.Ordinal))).Order(StringComparer.Ordinal).Take(128);
        var values = new JsonObject();
        foreach (var name in SafeValues)
        {
            if (environment.TryGetValue(name, out var value) && value is not null)
            {
                values[name] = new string(value.Where(character => !char.IsControl(character)).Take(256).ToArray());
            }
        }
        return new JsonObject
        {
            ["names"] = Strings(names),
            ["values"] = values,
            ["proxy_variables_set"] = Strings(ProxyNames.Where(name => environment.TryGetValue(name, out var value) &&
                !string.IsNullOrEmpty(value)).Order(StringComparer.Ordinal)),
        };
    }

    internal static Uri? SafeEndpoint(string? value) =>
        value?.Length <= 2048 && Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == Uri.UriSchemeHttps &&
        uri.UserInfo.Length == 0 && uri.Query.Length == 0 && uri.Fragment.Length == 0 ? uri : null;

    internal static JsonArray Strings(IEnumerable<string> values) => new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());
    private static IPNetwork[] Networks(params string[] values) => values.Select(IPNetwork.Parse).ToArray();
}

/// <summary>A configured host and optional independent HTTP-client check, never an arbitrary user-supplied URL.</summary>
public sealed record DiagnosticTarget(string Host, string? HttpPath = null);
