using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Hosting;

/// <summary>RSA keys stay in memory; no token or private key reaches a file, log or validation lookup.</summary>
public sealed class ContractTokenMinter(IClock clock) : ITokenMinter, IContractSigningKey, IDisposable
{
    private readonly RSA _main = RSA.Create(2048);
    private readonly RSA _other = RSA.Create(2048);
    private readonly object _lock = new();

    /// <inheritdoc />
    public string Mint(JsonElement specification)
    {
        var kind = Text(specification, "kind", "user");
        const string tenant = "00000000-0000-0000-0000-0000000000aa";
        const string client = "11111111-2222-3333-4444-555555555555";
        var oid = Text(specification, "oid", kind == "user"
            ? "00000000-0000-0000-0000-0000000000a1" : "00000000-0000-0000-0000-0000000000b1");
        var now = clock.UtcNow.ToUnixTimeSeconds();
        var claims = new JsonObject
        {
            ["aud"] = Text(specification, "aud", client),
            ["iss"] = Text(specification, "iss", $"https://login.microsoftonline.com/{tenant}/v2.0"),
            ["iat"] = now,
            ["nbf"] = now + Number(specification, "nbf_in", 0),
            ["exp"] = now + Number(specification, "exp_in", 3600),
            ["oid"] = oid,
            ["tid"] = Text(specification, "tid", tenant),
        };
        AddShape(specification, kind, oid, claims);
        if (specification.TryGetProperty("claims", out var overrides) && overrides.ValueKind == JsonValueKind.Object)
        {
            foreach (var claim in overrides.EnumerateObject())
            {
                claims[claim.Name] = JsonNode.Parse(claim.Value.GetRawText());
            }
        }

        if (specification.TryGetProperty("drop", out var drop))
        {
            foreach (var claim in drop.EnumerateArray())
            {
                claims.Remove(claim.GetString()!);
            }
        }

        return Sign(claims, Text(specification, "key", "main") == "main" ? _main : _other);
    }

    private static void AddShape(JsonElement spec, string kind, string oid, JsonObject claims)
    {
        claims["roles"] = spec.TryGetProperty("roles", out var roles)
            ? JsonNode.Parse(roles.GetRawText()) : new JsonArray(kind == "user" ? "TCC.User" : "TCC.Agent");
        if (kind == "user")
        {
            claims["preferred_username"] = Text(spec, "upn", "analyst@example.test");
            claims["name"] = Text(spec, "name", "Ana Lyst");
            claims["scp"] = Text(spec, "scp", "user_impersonation");
        }
        else
        {
            claims["idtyp"] = "app";
            claims["sub"] = oid;
        }
    }

    private string Sign(JsonObject claims, RSA key)
    {
        var header = Encode(Encoding.UTF8.GetBytes("""{"alg":"RS256","typ":"JWT","kid":"contract-key"}"""));
        var payload = Encoding.UTF8.GetBytes(claims.ToJsonString());
        var signingInput = header + "." + Encode(payload);
        lock (_lock)
        {
            return signingInput + "." + Encode(key.SignData(Encoding.ASCII.GetBytes(signingInput), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1));
        }
    }

    private static string Text(JsonElement spec, string name, string fallback) =>
        spec.TryGetProperty(name, out var value) ? value.GetString()! : fallback;

    private static long Number(JsonElement spec, string name, long fallback) =>
        spec.TryGetProperty(name, out var value) ? value.GetInt64() : fallback;

    private static string Encode(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    /// <inheritdoc />
    public byte[] ExportPublicKey()
    {
        lock (_lock)
        {
            return _main.ExportSubjectPublicKeyInfo();
        }
    }

    /// <inheritdoc />
    public void Dispose()
    {
        _main.Dispose();
        _other.Dispose();
    }
}
