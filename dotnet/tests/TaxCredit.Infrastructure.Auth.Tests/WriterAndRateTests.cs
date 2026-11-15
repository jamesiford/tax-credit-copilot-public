using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class WriterAndRateTests
{
    [Fact]
    public async Task BrokenAllowlistDeniesAndLogsOnlyClassificationWhileAnotherSourceCanGrant()
    {
        var logged = new List<(string, string)>();
        var events = new AuthEvents((source, error) => logged.Add((source, error)));
        var broken = new Roster(failure: true);
        var wrapper = new DenyOnFailure(broken, "allowlist", events);
        Assert.False(await wrapper.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(new[] { ("allowlist", "InvalidOperationException") }, logged);
        Assert.Equal(1, events.DenialCounts["allowlist"]);
        Assert.DoesNotContain(TokenWorld.Writer, string.Join("", logged), StringComparison.Ordinal);
        var yes = new Roster(TokenWorld.Writer);
        var unused = new Roster(TokenWorld.Writer);
        var either = new EitherEntitlement([("broken", broken), ("roster", yes), ("unused", unused)], events);
        Assert.True(await either.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, yes.Calls); Assert.Equal(0, unused.Calls);
    }

    [Theory]
    [InlineData("yes")]
    [InlineData(null)]
    [InlineData(1)]
    public async Task TruthyNonBooleanProvidersCannotGrant(object? answer)
    {
        var events = new AuthEvents();
        var strict = new StrictWriterSource((_, _) => ValueTask.FromResult(answer));
        Assert.False(await new DenyOnFailure(strict, "allowlist", events).IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, events.DenialCounts["allowlist"]);
    }

    [Fact]
    public async Task AllSourcesBrokenDenyAndLogEachSource()
    {
        var events = new AuthEvents();
        var either = new EitherEntitlement([("one", new Roster(failure: true)), ("two", new Roster(failure: true))], events);
        Assert.False(await either.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, events.DenialCounts["one"]); Assert.Equal(1, events.DenialCounts["two"]);
    }

    [Fact]
    public async Task LoggerOutageCannotHideAnIndependentGrant()
    {
        var events = new AuthEvents((_, _) => throw new IOException("logger down"));
        var either = new EitherEntitlement([("broken", new Roster(failure: true)), ("roster", new Roster(TokenWorld.Writer))], events);
        Assert.True(await either.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(1, events.DenialCounts["broken"]);
    }

    [Fact]
    public async Task GroupFailuresAreNotCachedAndCacheExpiresExactlyAtOneMinute()
    {
        var clock = new ManualClock();
        var provider = new Membership { Failures = 1 };
        var events = new AuthEvents();
        using var group = new EntraGroupEntitlement(TokenWorld.Tenant, provider, events, clock);
        Assert.False(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.True(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.True(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(2, provider.Calls);
        clock.Seconds = 59.999;
        Assert.True(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(2, provider.Calls);
        clock.Seconds = 60;
        provider.Answer = false;
        Assert.False(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.False(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(3, provider.Calls);
        Assert.Equal(1, events.DenialCounts["entra_group"]);
        group.Reset();
        Assert.False(await group.IsWriterAsync(TokenWorld.Writer));
        Assert.Equal(4, provider.Calls);
    }

    [Fact]
    public async Task GroupCachesAreIsolatedBoundedAndCoalesceConcurrentChecks()
    {
        var provider = new Membership();
        using var group = new EntraGroupEntitlement(TokenWorld.Tenant, provider, new AuthEvents(), maxEntries: 1);
        Assert.All(await Task.WhenAll(Enumerable.Range(0, 50).Select(async _ => await group.IsWriterAsync(TokenWorld.Writer))), Assert.True);
        Assert.Equal(1, provider.Calls);
        await group.IsWriterAsync(TokenWorld.Reader);
        await group.IsWriterAsync(TokenWorld.Writer);
        Assert.Equal(3, provider.Calls);
        using var other = new EntraGroupEntitlement(TokenWorld.Client, provider, new AuthEvents());
        await other.IsWriterAsync(TokenWorld.Writer);
        Assert.Equal(4, provider.Calls);
    }

    [Fact]
    public async Task AgentAuthorMustMatchActingUserAndBotRightsCannotSubstitute()
    {
        var principal = AgentFor(TokenWorld.Writer);
        var onlyBot = new WriterPolicy(new Roster(TokenWorld.Agent));
        Assert.Equal("writer_forbidden", (await Assert.ThrowsAsync<ApiAuthException>(async () => await onlyBot.CheckAsync(principal, principal.Actor, true))).Code);
        var policy = new WriterPolicy(new Roster(TokenWorld.Writer));
        Assert.Equal("author_mismatch", (await Assert.ThrowsAsync<ApiAuthException>(async () => await policy.CheckAsync(principal, "other", true))).Code);
        await policy.CheckAsync(principal, principal.Actor, true);
        await policy.CheckAsync(principal, null, false);
        Assert.Equal("missing_acting_user", (await Assert.ThrowsAsync<ApiAuthException>(async () => await policy.CheckAsync(principal with { ActingFor = null }, "other", true))).Code);
    }

    [Fact]
    public async Task UsersAndAnonymousKeepExistingWritesUnlessExplicitlyEnforced()
    {
        var principal = new ApiPrincipal(Oid: TokenWorld.Writer, Authenticated: true);
        var roster = new Roster();
        await new WriterPolicy(roster).CheckAsync(principal, principal.Actor, true);
        await new WriterPolicy(roster).CheckAsync(ApiPrincipal.Anonymous, "local-user", true);
        var strict = new WriterPolicy(roster, true);
        Assert.Equal("writer_forbidden", (await Assert.ThrowsAsync<ApiAuthException>(async () => await strict.CheckAsync(principal, principal.Actor, true))).Code);
        Assert.Equal("writer_forbidden", (await Assert.ThrowsAsync<ApiAuthException>(async () => await strict.CheckAsync(ApiPrincipal.Anonymous, "local-user", true))).Code);
        Assert.Equal("local-user", ApiPrincipal.Anonymous.Attributed(" local-user "));
    }

    [Fact]
    public void LimiterDepletionRefillAndRetryArithmeticMatchFrozenP1()
    {
        var clock = new ManualClock();
        var limiter = new ApiRateLimiter(new(3), clock);
        var user = User(TokenWorld.Writer);
        Assert.True(limiter.Check("draft_save", user).Allowed);
        Assert.True(limiter.Check("draft_save", user).Allowed);
        Assert.True(limiter.Check("draft_save", user).Allowed);
        var denied = limiter.Check("draft_save", user);
        Assert.Equal(21, denied.RetryAfterSeconds);
        Assert.Equal("rate_limited", denied.Code);
        Assert.Contains("RATE_LIMIT_PER_MINUTE", denied.Remedy, StringComparison.Ordinal);
        var detail = System.Text.Json.JsonSerializer.SerializeToElement(denied);
        Assert.Equal(new[] { "code", "reason", "remedy" }, detail.EnumerateObject().Select(p => p.Name));
        clock.Seconds = 19;
        Assert.Equal(2, limiter.Check("draft_save", user).RetryAfterSeconds);
        clock.Seconds = 20;
        Assert.True(limiter.Check("draft_save", user).Allowed);
        Assert.Equal(21, limiter.Check("draft_save", user).RetryAfterSeconds);
        clock.Utc = clock.Utc.AddDays(1000);
        Assert.False(limiter.Check("draft_save", user).Allowed);
        clock.Seconds = 200;
        Assert.Equal(new[] { true, true, true, false }, Enumerable.Range(0, 4).Select(_ => limiter.Check("draft_save", user).Allowed));
    }

    [Fact]
    public void EachKindAndCallerOidHasIndependentAllowanceAndAgentsCannotSplitByActingPerson()
    {
        var limiter = new ApiRateLimiter(new(1), new ManualClock());
        Assert.True(limiter.Check("draft_save", AgentFor(TokenWorld.Writer)).Allowed);
        Assert.False(limiter.Check("draft_save", AgentFor(TokenWorld.Writer)).Allowed);
        Assert.False(limiter.Check("draft_save", AgentFor(TokenWorld.Reader)).Allowed);
        Assert.True(limiter.Check("draft_save", AgentFor(TokenWorld.Reader) with { Oid = "another-agent" }).Allowed);
        Assert.True(limiter.Check("draft_export", AgentFor(TokenWorld.Writer)).Allowed);
        Assert.True(limiter.Check("draft_save", User("another")).Allowed);
        Assert.All(Enumerable.Range(0, 100), _ => Assert.True(limiter.Check("draft_save", ApiPrincipal.Anonymous).Allowed));
        Assert.Equal(4, limiter.BucketCount);
    }

    [Fact]
    public async Task ConcurrentCallsCannotOverspendAndResetStartsAFreshScenario()
    {
        var limiter = new ApiRateLimiter(new(7), new ManualClock());
        var results = await Task.WhenAll(Enumerable.Range(0, 100).Select(_ => Task.Run(() => limiter.Check("batch_start", User(TokenWorld.Writer)))));
        Assert.Equal(7, results.Count(r => r.Allowed));
        Assert.All(results.Where(r => !r.Allowed), r => Assert.Equal(9, r.RetryAfterSeconds));
        limiter.Reset();
        Assert.Equal(0, limiter.BucketCount);
        Assert.True(limiter.Check("batch_start", User(TokenWorld.Writer)).Allowed);
    }

    [Fact]
    public void DepletedBucketsAreRetainedUntilFullAndClockRollbackCannotGrant()
    {
        var clock = new ManualClock();
        var limiter = new ApiRateLimiter(new(1, 2), clock);
        Assert.True(limiter.Check("kind", User("a")).Allowed);
        Assert.True(limiter.Check("kind", User("b")).Allowed);
        Assert.False(limiter.Check("kind", User("a")).Allowed);
        Assert.Equal(61, limiter.Check("kind", User("c")).RetryAfterSeconds);
        Assert.Equal(2, limiter.BucketCount);
        foreach (var caller in new[] { "a", "b", "c", "a", "b", "c" })
        {
            Assert.False(limiter.Check("kind", User(caller)).Allowed);
        }
        clock.Seconds = -100;
        Assert.False(limiter.Check("kind", User("b")).Allowed);
        clock.Seconds = 0;
        Assert.False(limiter.Check("kind", User("b")).Allowed);
        clock.Seconds = 59.999;
        Assert.Equal(1, limiter.Check("kind", User("c")).RetryAfterSeconds);
        clock.Seconds = 60;
        Assert.True(limiter.Check("kind", User("c")).Allowed);
        Assert.True(limiter.Check("kind", User("b")).Allowed);
        Assert.False(limiter.Check("kind", User("a")).Allowed);
        Assert.Equal(2, limiter.BucketCount);
    }

    [Fact]
    public void ZeroDisablesApiLimitAndInvalidSettingsAreRefused()
    {
        var limiter = new ApiRateLimiter(new(0), new ManualClock());
        Assert.All(Enumerable.Range(0, 100), _ => Assert.True(limiter.Check("kind", User(TokenWorld.Writer)).Allowed));
        Assert.Equal(0, limiter.BucketCount);
        Assert.Throws<ArgumentOutOfRangeException>(() => new ApiRateLimiter(new(-1)));
        Assert.Throws<ArgumentOutOfRangeException>(() => new ApiRateLimiter(new(1, 0)));
        Assert.Equal(60, ApiRateLimitOptions.Parse("junk").PerMinute);
        Assert.Equal(60, ApiRateLimitOptions.Parse(null).PerMinute);
        Assert.Equal(0, ApiRateLimitOptions.Parse("0").PerMinute);
    }

    private static ApiPrincipal User(string oid) => new(Oid: oid, Authenticated: true);
    private static ApiPrincipal AgentFor(string oid) => new(Oid: TokenWorld.Agent, Authenticated: true, PrincipalType: "agent",
        ActingFor: new ActingUser(oid, Upn: "writer@example.test"));

    private sealed class Roster(string? oid = null, bool failure = false) : IWriterEntitlement
    {
        internal int Calls { get; private set; }
        public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
        {
            Calls++;
            return failure ? throw new InvalidOperationException("not logged: secret identity") : ValueTask.FromResult(userOid == oid);
        }
    }
    private sealed class Membership : IGroupMembershipProvider
    {
        internal int Calls { get; private set; }
        internal int Failures { get; set; }
        internal bool Answer { get; set; } = true;
        public ValueTask<bool> IsMemberAsync(string userOid, string groupId, CancellationToken cancellationToken = default)
        {
            Calls++;
            return Failures-- > 0 ? throw new InvalidOperationException("private Graph payload") : ValueTask.FromResult(Answer);
        }
    }
}
