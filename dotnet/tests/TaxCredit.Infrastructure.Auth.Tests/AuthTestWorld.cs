using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace TaxCredit.Infrastructure.Auth.Tests;

internal sealed class ManualClock : TimeProvider
{
    internal DateTimeOffset Utc { get; set; } = DateTimeOffset.FromUnixTimeSeconds(1_768_478_400);
    internal double Seconds { get; set; }
    public override long TimestampFrequency => 1_000_000;
    public override long GetTimestamp() => (long)(Seconds * TimestampFrequency);
    public override DateTimeOffset GetUtcNow() => Utc;
}

internal sealed class TokenWorld : IDisposable
{
    internal const string Tenant = "00000000-0000-0000-0000-0000000000aa";
    internal const string Client = "11111111-2222-3333-4444-555555555555";
    internal const string Reader = "00000000-0000-0000-0000-0000000000a1";
    internal const string Writer = "00000000-0000-0000-0000-0000000000a2";
    internal const string Agent = "00000000-0000-0000-0000-0000000000b1";
    internal RSA Key { get; } = RSA.Create(2048);
    internal ManualClock Clock { get; } = new();
    internal AuthConfiguration Configuration { get; } = new() { TenantId = Tenant, ApiAudience = $"api://{Client}" };
    internal EntraTokenValidator Validator => new(Configuration, new FixedKeys(Key), Clock);

    internal Dictionary<string, object?> Claims(bool agent = false)
    {
        var now = Clock.GetUtcNow().ToUnixTimeSeconds();
        var claims = new Dictionary<string, object?>
        {
            ["aud"] = Client,
            ["iss"] = Configuration.Issuer,
            ["iat"] = now,
            ["nbf"] = now,
            ["exp"] = now + 3600,
            ["oid"] = agent ? Agent : Reader,
            ["tid"] = Tenant,
            ["roles"] = agent ? new[] { "TCC.Agent" } : new[] { "TCC.User" }
        };
        if (agent) { claims["idtyp"] = "app"; claims["sub"] = Agent; }
        else { claims["preferred_username"] = "analyst@example.test"; claims["name"] = "Analyst"; claims["scp"] = "user_impersonation"; }
        return claims;
    }

    internal string Mint(Dictionary<string, object?>? claims = null, string algorithm = "RS256", RSA? key = null)
    {
        var header = Url(JsonSerializer.SerializeToUtf8Bytes(new { alg = algorithm, kid = "test-key" }));
        var payload = Url(JsonSerializer.SerializeToUtf8Bytes(claims ?? Claims()));
        var data = Encoding.ASCII.GetBytes($"{header}.{payload}");
        return $"{header}.{payload}.{Url((key ?? Key).SignData(data, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))}";
    }

    internal string Jwks(string kid = "test-key")
    {
        var key = Key.ExportParameters(false);
        return JsonSerializer.Serialize(new { keys = new[] { new { kty = "RSA", kid, use = "sig", alg = "RS256", n = Url(key.Modulus!), e = Url(key.Exponent!) } } });
    }
    internal static string Header(Dictionary<string, object?>? values = null) => Url(JsonSerializer.SerializeToUtf8Bytes(values ??
        new() { ["oid"] = Writer, ["tid"] = Tenant, ["name"] = "Writer", ["upn"] = "writer@example.test", ["channel"] = "teams" }));
    internal static string Url(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
    public void Dispose() => Key.Dispose();
}

internal sealed class FixedKeys(RSA rsa) : ISigningKeyProvider
{
    public ValueTask<RSAParameters> GetKeyAsync(string keyId, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult(rsa.ExportParameters(false));
    public void Reset() { }
}
