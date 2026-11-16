using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class RegistrationAndScopeTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("azure")]
    [InlineData("test")]
    [InlineData("localhost")]
    public void AnonymousWithoutExplicitLocalOrSyntheticDemoIsRefused(string? environment) =>
        Assert.Throws<ArgumentException>(() => new AuthConfiguration { Mode = "none", Environment = environment }.Validate());

    [Theory]
    [InlineData("local")]
    [InlineData(" LOCAL ")]
    public void ExplicitLocalAnonymousOptInWorks(string environment) =>
        new AuthConfiguration { Mode = "none", Environment = environment }.Validate();

    [Fact]
    public void SyntheticFlagCannotCoverCustomerDataOrDisableEntra()
    {
        Assert.Throws<ArgumentException>(() => new AuthConfiguration
        { Mode = "none", Environment = "azure", DataClassification = "customer", AllowAnonymousSynthetic = true }.Validate());
        Assert.Throws<ArgumentException>(() => new AuthConfiguration
        { Mode = "entra", Environment = "azure", DataClassification = "synthetic", AllowAnonymousSynthetic = true }.Validate());
        new AuthConfiguration { Mode = "none", Environment = "azure", DataClassification = "synthetic", AllowAnonymousSynthetic = true }.Validate();
    }

    [Fact]
    public void DefaultMissingConfigurationAndUnknownAuthModesFailStartup()
    {
        Assert.Throws<ArgumentException>(() => new AuthConfiguration().Validate());
        Assert.Throws<ArgumentException>(() => new AuthConfiguration { Mode = "basic" }.Validate());
    }

    [Fact]
    public async Task RegistrationPreservesInjectedKeysAndExposesApplicationOnlyPorts()
    {
        using var world = new TokenWorld();
        using var http = new HttpClient();
        var services = new ServiceCollection();
        services.AddSingleton<ISigningKeyProvider>(new FixedKeys(world.Key));
        services.AddSingleton<TimeProvider>(world.Clock);
        services.AddTaxCreditAuth(world.Configuration, http, new(1));
        services.AddTaxCreditAuth(world.Configuration, http, new(1));
        Assert.Throws<ArgumentException>(() => services.AddTaxCreditAuth(world.Configuration with { EnforceWriterForUsers = true }, http, new(1)));
        Assert.Throws<ArgumentException>(() => services.AddTaxCreditAuth(world.Configuration, http, new(2)));
        using var provider = services.BuildServiceProvider();
        Assert.IsType<FixedKeys>(provider.GetRequiredService<ISigningKeyProvider>());
        var trust = provider.GetRequiredService<IApiTrustService>();
        Assert.True((await trust.AuthenticateAsync("/api/me", $"Bearer {world.Mint()}", null)).Authenticated);
        Assert.NotNull(provider.GetRequiredService<IWriterPolicy>());
        var limiter = provider.GetRequiredService<IApiRateLimiter>();
        Assert.Same(limiter, provider.GetRequiredService<IApiRateLimiter>());
        var user = new ApiPrincipal(Oid: TokenWorld.Reader, Authenticated: true);
        Assert.True(limiter.Check("save", user).Allowed);
        Assert.False(limiter.Check("save", user).Allowed);
        limiter.Reset();
        Assert.True(limiter.Check("save", user).Allowed);
    }

    [Fact]
    public async Task WriterRegistrationIsSafeByDefaultAndUnknownSourcesAreRefused()
    {
        using var world = new TokenWorld();
        using var http = new HttpClient();
        var services = new ServiceCollection();
        services.AddTaxCreditAuth(world.Configuration with { EnforceWriterForUsers = true }, http);
        services.AddTaxCreditWriters("either", new BrokenRoster(), new Member(), TokenWorld.Tenant);
        using var provider = services.BuildServiceProvider();
        Assert.True(await provider.GetRequiredService<IWriterEntitlement>().IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, Assert.IsType<AuthEvents>(provider.GetRequiredService<IAuthEvents>()).DenialCounts["allowlist"]);
        Assert.Throws<ArgumentException>(() => new ServiceCollection().AddTaxCreditWriters("everyone", new BrokenRoster()));
        Assert.Throws<ArgumentException>(() => new ServiceCollection().AddTaxCreditWriters("entra_group", new BrokenRoster()));
    }

    [Fact]
    public async Task AmbientScopeIsRestoredAndSeparateAsyncRequestsCannotBorrowIdentity()
    {
        var accessor = new ApiPrincipalAccessor();
        Assert.Null(accessor.Current);
        using (accessor.Push(new(Oid: TokenWorld.Reader, Authenticated: true)))
        {
            using (accessor.Push(new(Oid: TokenWorld.Writer, Authenticated: true)))
            {
                Assert.Equal(TokenWorld.Writer, accessor.Current!.Oid);
            }
            Assert.Equal(TokenWorld.Reader, accessor.Current!.Oid);
            var callers = await Task.WhenAll(Enumerable.Range(0, 20).Select(async index =>
            {
                using var scope = accessor.Push(new(Oid: index.ToString(System.Globalization.CultureInfo.InvariantCulture)));
                await Task.Yield();
                return accessor.Current!.Oid;
            }));
            Assert.Equal(Enumerable.Range(0, 20).Select(i => i.ToString(System.Globalization.CultureInfo.InvariantCulture)), callers);
            Assert.Equal(TokenWorld.Reader, accessor.Current!.Oid);
        }
        Assert.Null(accessor.Current);
    }

    private sealed class BrokenRoster : IWriterEntitlement
    {
        public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default) => throw new IOException("not logged");
    }
    private sealed class Member : IGroupMembershipProvider
    {
        public ValueTask<bool> IsMemberAsync(string userOid, string groupId, CancellationToken cancellationToken = default) => ValueTask.FromResult(true);
    }
}
