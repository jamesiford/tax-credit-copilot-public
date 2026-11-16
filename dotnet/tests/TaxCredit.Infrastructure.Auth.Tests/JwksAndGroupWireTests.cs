using System.Net;
using System.Text;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class JwksAndGroupWireTests
{
    [Fact]
    public async Task RotationRefreshFailureCooldownAndResetAreBounded()
    {
        using var world = new TokenWorld();
        var transport = new JwksTransport(world.Jwks());
        using var keys = new CachedJwksProvider(transport, world.Clock);
        var first = await keys.GetKeyAsync("test-key");
        first.Modulus![0] ^= 1;
        Assert.NotEqual(first.Modulus, (await keys.GetKeyAsync("test-key")).Modulus);
        Assert.Equal(1, transport.Calls);
        Assert.Equal("unknown_key", (await Assert.ThrowsAsync<AuthRefusalException>(async () => await keys.GetKeyAsync("rotated"))).Code);
        Assert.Equal(1, transport.Calls);
        world.Clock.Seconds = 5;
        transport.Body = world.Jwks("rotated");
        Assert.NotNull((await keys.GetKeyAsync("rotated")).Modulus);
        Assert.Equal(2, transport.Calls);
        world.Clock.Seconds = 3606; transport.Fail = true;
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await keys.GetKeyAsync("rotated"));
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await keys.GetKeyAsync("rotated"));
        Assert.Equal(3, transport.Calls);
        world.Clock.Seconds += 5; transport.Fail = false;
        await keys.GetKeyAsync("rotated");
        Assert.Equal(4, transport.Calls);
        keys.Reset();
        await keys.GetKeyAsync("rotated");
        Assert.Equal(5, transport.Calls);
    }

    [Theory]
    [InlineData("{}")]
    [InlineData("{\"keys\":[]}")]
    [InlineData("{\"keys\":\"not-array\"}")]
    [InlineData("not-json")]
    [InlineData("{\"keys\":[{\"kty\":\"RSA\",\"kid\":\"x\",\"n\":\"!!!\",\"e\":\"AQAB\"}]}")]
    public async Task MalformedKeySetsAreTypedUnavailableAndNotCached(string body)
    {
        var clock = new ManualClock();
        var transport = new JwksTransport(body);
        using var keys = new CachedJwksProvider(transport, clock);
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await keys.GetKeyAsync("x"));
        clock.Seconds = 5;
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await keys.GetKeyAsync("x"));
        Assert.Equal(2, transport.Calls);
    }

    [Fact]
    public async Task ConcurrentKnownKeyRefreshIsCoalesced()
    {
        using var world = new TokenWorld();
        var transport = new JwksTransport(world.Jwks());
        using var keys = new CachedJwksProvider(transport, world.Clock);
        var values = await Task.WhenAll(Enumerable.Range(0, 100).Select(async _ => await keys.GetKeyAsync("test-key")));
        Assert.All(values, key => Assert.NotNull(key.Modulus));
        Assert.Equal(1, transport.Calls);
    }

    [Fact]
    public async Task ConfiguredJwksRetrievalUsesTenantUriAndNeverTokenControlledUrls()
    {
        using var world = new TokenWorld();
        Uri? seen = null;
        using var client = new HttpClient(new FakeHandler(request =>
        {
            seen = request.RequestUri;
            return new(HttpStatusCode.OK) { Content = new StringContent(world.Jwks()) };
        }));
        var transport = new HttpJwksTransport(client, world.Configuration);
        using var keys = new CachedJwksProvider(transport, world.Clock);
        var validator = new EntraTokenValidator(world.Configuration, keys, world.Clock);
        Assert.True((await validator.ValidateAsync(world.Mint())).Authenticated);
        Assert.Equal(world.Configuration.JwksUri, seen);
    }

    [Theory]
    [InlineData(500)]
    [InlineData(403)]
    public async Task JwksHttpFailuresDoNotLeakUpstreamBody(int status)
    {
        using var world = new TokenWorld();
        using var client = new HttpClient(new FakeHandler(_ => new((HttpStatusCode)status)
        { Content = new StringContent("private upstream body") }));
        var transport = new HttpJwksTransport(client, world.Configuration);
        var error = await Assert.ThrowsAsync<AuthDependencyException>(async () => await transport.FetchAsync());
        Assert.DoesNotContain("private upstream body", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task JwksBodyLimitAndCallerCancellationPropagate()
    {
        using var world = new TokenWorld();
        using var client = new HttpClient(new FakeHandler(_ => new(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[1_048_577]) }));
        var transport = new HttpJwksTransport(client, world.Configuration);
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await transport.FetchAsync());
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await transport.FetchAsync(cancellation.Token));
    }

    [Fact]
    public async Task GroupWireBindsGuidIdsFixedScopeAndBearerThenRefreshesOnceOnPermissionFailure()
    {
        var calls = 0;
        var tokens = new Tokens();
        using var client = new HttpClient(new FakeHandler(request =>
        {
            calls++;
            Assert.Equal($"https://graph.microsoft.com/v1.0/users/{TokenWorld.Writer}/checkMemberGroups", request.RequestUri!.AbsoluteUri);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal($"fake-{calls}", request.Headers.Authorization.Parameter);
            var body = request.Content!.ReadAsStringAsync().GetAwaiter().GetResult();
            Assert.Contains(TokenWorld.Tenant, body, StringComparison.Ordinal);
            return calls == 1 ? new(HttpStatusCode.Forbidden) { Content = new StringContent("{\"error\":{\"code\":\"Authorization_RequestDenied\"}}") } :
                new(HttpStatusCode.OK) { Content = new StringContent($"{{\"value\":[\"{TokenWorld.Tenant.ToUpperInvariant()}\"]}}") };
        }));
        var provider = new GraphGroupMembershipProvider(client, tokens);
        Assert.True(await provider.IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        Assert.Equal(2, calls); Assert.Equal(1, tokens.Invalidations);
        Assert.All(tokens.Scopes, scope => Assert.Equal(GraphGroupMembershipProvider.Scope, scope));
    }

    [Theory]
    [InlineData("{\"value\":[]}", false)]
    [InlineData("{\"value\":[\"00000000-0000-0000-0000-0000000000aa\"]}", true)]
    public async Task GroupWireReturnsExplicitMembershipVerdict(string body, bool member)
    {
        using var client = new HttpClient(new FakeHandler(_ => new(HttpStatusCode.OK) { Content = new StringContent(body) }));
        Assert.Equal(member, await new GraphGroupMembershipProvider(client, new Tokens()).IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
    }

    [Fact]
    public async Task PermanentPermissionDenialRefreshesAtMostOnceAMinuteAndUnclassified403NeverRefreshes()
    {
        var calls = 0;
        var tokens = new Tokens();
        var clock = new ManualClock();
        using var client = new HttpClient(new FakeHandler(_ =>
        {
            calls++;
            return new(HttpStatusCode.Forbidden)
            {
                Content = new StringContent("{\"error\":{\"code\":\"Authorization_RequestDenied\"}}")
            };
        }));
        var provider = new GraphGroupMembershipProvider(client, tokens, clock);
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await provider.IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await provider.IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        Assert.Equal(3, calls); Assert.Equal(1, tokens.Invalidations);
        clock.Seconds = 60;
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await provider.IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        Assert.Equal(5, calls); Assert.Equal(2, tokens.Invalidations);
        using var unclassified = new HttpClient(new FakeHandler(_ => new(HttpStatusCode.Forbidden) { Content = new StringContent("{}") }));
        await Assert.ThrowsAsync<AuthDependencyException>(async () => await new GraphGroupMembershipProvider(unclassified, tokens).IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        Assert.Equal(2, tokens.Invalidations);
    }

    [Theory]
    [InlineData("{\"value\":\"truthy\"}")]
    [InlineData("{}")]
    [InlineData("{\"value\":[12]}")]
    [InlineData("not-json")]
    [InlineData("{\"value\":[],\"value\":[\"00000000-0000-0000-0000-0000000000aa\"]}")]
    public async Task GroupMalformedHttpRepliesFailClosedWithOnlySafeEvents(string body)
    {
        using var client = new HttpClient(new FakeHandler(_ => new(HttpStatusCode.OK) { Content = new StringContent(body) }));
        var events = new AuthEvents();
        using var group = new EntraGroupEntitlement(TokenWorld.Tenant, new GraphGroupMembershipProvider(client, new Tokens()), events);
        Assert.False(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, events.DenialCounts["entra_group"]);
    }

    [Fact]
    public async Task GraphTransportAndCredentialErrorsNeverCarryRawInnerExceptions()
    {
        using var client = new HttpClient(new FakeHandler(_ => throw new HttpRequestException("private raw transport",
            new IOException("private raw inner"))));
        var error = await Assert.ThrowsAsync<AuthDependencyException>(async () =>
            await new GraphGroupMembershipProvider(client, new Tokens()).IsMemberAsync(TokenWorld.Writer, TokenWorld.Tenant));
        Assert.Null(error.InnerException);
        Assert.DoesNotContain("private raw", error.ToString(), StringComparison.Ordinal);
    }

    private sealed class JwksTransport(string body) : IJwksTransport
    {
        internal string Body { get; set; } = body;
        internal int Calls { get; private set; }
        internal bool Fail { get; set; }
        public ValueTask<ReadOnlyMemory<byte>> FetchAsync(CancellationToken cancellationToken = default)
        {
            Calls++;
            return Fail ? throw new AuthDependencyException("jwks_unavailable") : ValueTask.FromResult<ReadOnlyMemory<byte>>(Encoding.UTF8.GetBytes(Body));
        }
    }
    private sealed class FakeHandler(Func<HttpRequestMessage, HttpResponseMessage> response) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(response(request));
        }
    }
    private sealed class Tokens : IAuthAccessTokenProvider
    {
        internal List<string> Scopes { get; } = [];
        internal int Invalidations { get; private set; }
        public ValueTask<string> GetTokenAsync(string scope, CancellationToken cancellationToken = default)
        {
            Scopes.Add(scope); return ValueTask.FromResult($"fake-{Scopes.Count}");
        }
        public bool Invalidate(string scope) { Invalidations++; return true; }
    }
}
