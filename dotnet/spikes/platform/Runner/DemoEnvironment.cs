using Microsoft.Data.SqlClient;

namespace PlatformSpike;

internal sealed class DemoEnvironment
{
    internal const string FilePath = @"C:\Projects\GitHub\tax-credit-copilot-public\backend\.env";
    private readonly Dictionary<string, string> values = new(StringComparer.Ordinal);
    internal string Get(string key, string fallback = "") => values.GetValueOrDefault(key, fallback);
    internal string Require(string key) => Get(key) is { Length: > 0 } value
        ? value : throw new InvalidOperationException($"Required configuration key missing: {key}.");

    internal DemoEnvironment()
    {
        if (Environment.GetEnvironmentVariable("SPIKE_PLATFORM_APPROVED") != "yes")
            throw new GuardRefusal("SPIKE_PLATFORM_APPROVED must be yes.");
        foreach (var line in File.ReadLines(FilePath))
        {
            var text = line.Trim();
            if (text.StartsWith('#') || !text.Contains('=', StringComparison.Ordinal)) continue;
            var parts = text.Split('=', 2);
            values[parts[0].Trim()] = parts[1].Trim().Trim('"', '\'');
        }
        _ = Require("FABRIC_WORKSPACE");
        _ = Require("FABRIC_LAKEHOUSE");
    }

    internal string ConnectionString(bool lakehouse = false, bool defaultAuth = false, bool pooling = true,
        int retryCount = 1)
    {
        var builder = new SqlConnectionStringBuilder
        {
            DataSource = lakehouse ? Get("LAKEHOUSE_SQL_SERVER", Require("WAREHOUSE_SERVER")) : Require("WAREHOUSE_SERVER"),
            InitialCatalog = lakehouse ? Get("LAKEHOUSE_SQL_DATABASE", Require("FABRIC_LAKEHOUSE")) : Require("WAREHOUSE_DATABASE"),
            Encrypt = SqlConnectionEncryptOption.Mandatory,
            TrustServerCertificate = false,
            ConnectTimeout = 90,
            Pooling = pooling,
            MaxPoolSize = 4,
            ConnectRetryCount = retryCount,
            ConnectRetryInterval = 2
        };
        if (defaultAuth) builder.Authentication = SqlAuthenticationMethod.ActiveDirectoryDefault;
        return builder.ConnectionString;
    }

    internal string Redact(string message)
    {
        foreach (var value in values.Values.Where(v => v.Length >= 4).OrderByDescending(v => v.Length))
            message = message.Replace(value, "[redacted]", StringComparison.OrdinalIgnoreCase);
        return message;
    }
}
