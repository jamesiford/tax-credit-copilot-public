using System.Security.Cryptography;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class TokenValidationTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BothAudienceFormsPreserveApiIdentity(bool uri)
    {
        using var world = new TokenWorld();
        var claims = world.Claims();
        claims["aud"] = uri ? $"api://{TokenWorld.Client}" : TokenWorld.Client;
        var principal = await world.Validator.ValidateAsync(world.Mint(claims));
        Assert.True(principal.Authenticated);
        Assert.Equal(TokenWorld.Reader, principal.Oid);
        Assert.Equal("analyst@example.test", principal.Actor);
        Assert.Equal(new[] { "TCC.User" }, principal.Roles);
        Assert.Equal(new[] { "user_impersonation" }, principal.Scopes);
        Assert.Null(principal.ActingFor);
    }

    [Theory]
    [InlineData("exp")]
    [InlineData("iat")]
    [InlineData("iss")]
    [InlineData("aud")]
    public async Task RequiredClaimsAreAuthenticationFailures(string field)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(); claims.Remove(field);
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(claims)));
        Assert.Equal(401, error.StatusCode);
        Assert.Equal("Bearer", error.Challenge);
    }

    [Theory]
    [InlineData("aud", "api://contract-gateway")]
    [InlineData("iss", "https://sts.windows.net/00000000-0000-0000-0000-0000000000aa/")]
    [InlineData("iss", "https://login.microsoftonline.com/00000000-0000-0000-0000-0000000000bb/v2.0")]
    [InlineData("tid", "00000000-0000-0000-0000-0000000000bb")]
    [InlineData("tid", "not-a-guid")]
    public async Task WrongResourceIssuerOrTenantCannotProveApiIdentity(string field, string value)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(); claims[field] = value;
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(claims)));
        Assert.Equal(401, error.StatusCode);
    }

    [Theory]
    [InlineData("exp", -59, true)]
    [InlineData("exp", -60, false)]
    [InlineData("exp", -61, false)]
    [InlineData("nbf", 60, true)]
    [InlineData("nbf", 61, false)]
    [InlineData("iat", 60, true)]
    [InlineData("iat", 61, false)]
    public async Task SixtySecondLifetimeEdgesMatchPython(string field, int offset, bool valid)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(); claims[field] = world.Clock.GetUtcNow().ToUnixTimeSeconds() + offset;
        if (valid)
        {
            Assert.True((await world.Validator.ValidateAsync(world.Mint(claims))).Authenticated);
        }
        else
        {
            Assert.Equal(401, (await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(claims)))).StatusCode);
        }
    }

    [Theory]
    [InlineData("HS256")]
    [InlineData("none")]
    [InlineData("RS512")]
    public async Task RefusedAlgorithmsNeverAcquireKeys(string algorithm)
    {
        using var world = new TokenWorld();
        var keys = new ThrowingKeys();
        var validator = new EntraTokenValidator(world.Configuration, keys, world.Clock);
        Assert.Equal(401, (await Assert.ThrowsAsync<ApiAuthException>(async () => await validator.ValidateAsync(world.Mint(algorithm: algorithm)))).StatusCode);
        Assert.Equal(0, keys.Calls);
    }

    [Fact]
    public async Task ForgedSignatureIs401WithoutPayloadLeakage()
    {
        using var world = new TokenWorld();
        using var other = RSA.Create(2048);
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(key: other)));
        Assert.Equal("signature", error.Code);
        Assert.DoesNotContain(TokenWorld.Reader, error.ToString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("not-a-jwt")]
    [InlineData("e30.e30.!!!")]
    [InlineData("e30.W10.AA")]
    public async Task MalformedTokensAreNeverAnonymous(string? token)
    {
        using var world = new TokenWorld();
        Assert.Equal(401, (await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(token))).StatusCode);
    }

    [Theory]
    [InlineData("roles")]
    [InlineData("scp")]
    [InlineData("oid")]
    [InlineData("exp")]
    public async Task MalformedClaimTypesAreControlled(string field)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(); claims[field] = new { unsupported = true };
        Assert.Equal(401, (await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(claims)))).StatusCode);
    }

    [Theory]
    [InlineData("scope", false)]
    [InlineData("user-role", false)]
    [InlineData("agent-role", false)]
    [InlineData("agent-no-role", true)]
    [InlineData("agent-user-role", true)]
    [InlineData("mixed-scope", true)]
    [InlineData("mixed-name", true)]
    public async Task ProvenButMissingOrMixedShapeIs403(string scenario, bool agent)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(agent);
        switch (scenario)
        {
            case "scope": claims["scp"] = "Channel.Access"; break;
            case "user-role": claims["roles"] = Array.Empty<string>(); break;
            case "agent-role": claims["roles"] = new[] { "TCC.User", "TCC.Agent" }; break;
            case "agent-no-role": claims["roles"] = Array.Empty<string>(); break;
            case "agent-user-role": claims["roles"] = new[] { "TCC.Agent", "TCC.User" }; break;
            case "mixed-scope": claims["scp"] = "user_impersonation"; break;
            case "mixed-name": claims["name"] = "Named person"; break;
        }
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await world.Validator.ValidateAsync(world.Mint(claims)));
        Assert.Equal(403, error.StatusCode);
        Assert.Null(error.Challenge);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AppShapeSupportsDocumentedSubjectFallbackOnly(bool idtyp)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(true);
        if (!idtyp)
        {
            claims.Remove("idtyp");
        }

        var principal = await world.Validator.ValidateAsync(world.Mint(claims));
        Assert.True(principal.IsAgent);
        Assert.Equal(TokenWorld.Agent, principal.Oid);
        Assert.Equal("anonymous", principal.Actor);
        Assert.Null(principal.EffectiveOid);
    }

    [Fact]
    public async Task KeyOutageIsTypedAndCancellationIsNotAuthenticationFailure()
    {
        using var world = new TokenWorld();
        var keys = new ThrowingKeys();
        var validator = new EntraTokenValidator(world.Configuration, keys);
        Assert.Equal("jwks_unavailable", (await Assert.ThrowsAsync<AuthDependencyException>(async () => await validator.ValidateAsync(world.Mint()))).Code);
        keys.Cancel = true;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await validator.ValidateAsync(world.Mint()));
    }

    private sealed class ThrowingKeys : ISigningKeyProvider
    {
        internal int Calls { get; private set; }
        internal bool Cancel { get; set; }
        public ValueTask<RSAParameters> GetKeyAsync(string keyId, CancellationToken cancellationToken = default)
        {
            Calls++;
            throw Cancel ? new OperationCanceledException(cancellationToken) : new AuthDependencyException("jwks_unavailable");
        }
        public void Reset() { }
    }
}
