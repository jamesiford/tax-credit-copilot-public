using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class RateBucketLifecycleTests
{
    [Fact]
    public void APartiallyRefilledBucketCannotBeEvictedForARepeatedFreshBurst()
    {
        var clock = new ManualClock();
        var limiter = new ApiRateLimiter(new(3, 1), clock);
        Assert.All(Enumerable.Range(0, 3), _ => Assert.True(limiter.Check("kind", User("a")).Allowed));
        Assert.False(limiter.Check("kind", User("b")).Allowed);
        clock.Seconds = 20;
        Assert.Equal(41, limiter.Check("kind", User("b")).RetryAfterSeconds);
        Assert.True(limiter.Check("kind", User("a")).Allowed);
        Assert.False(limiter.Check("kind", User("a")).Allowed);
        Assert.False(limiter.Check("kind", User("b")).Allowed);
        clock.Seconds = 80;
        Assert.All(Enumerable.Range(0, 3), _ => Assert.True(limiter.Check("kind", User("b")).Allowed));
        Assert.False(limiter.Check("kind", User("a")).Allowed);
        Assert.Equal(1, limiter.BucketCount);
    }

    [Fact]
    public async Task ConcurrentNewKeysCannotForceDepletedBucketEviction()
    {
        var limiter = new ApiRateLimiter(new(2, 1), new ManualClock());
        var results = await Task.WhenAll(Enumerable.Range(0, 100).Select(index => Task.Run(() =>
            limiter.Check("kind", User(index.ToString(System.Globalization.CultureInfo.InvariantCulture))))));
        Assert.Single(results, result => result.Allowed);
        Assert.Equal(1, limiter.BucketCount);
    }

    [Fact]
    public void SignedInCallersCannotSubstituteActorForMissingOid()
    {
        var limiter = new ApiRateLimiter(new(1), new ManualClock());
        var error = Assert.Throws<AuthRefusalException>(() => limiter.Check("kind", new(Upn: "analyst@example.test", Authenticated: true)));
        Assert.Equal(401, error.StatusCode);
        Assert.Equal(0, limiter.BucketCount);
    }

    private static ApiPrincipal User(string oid) => new(Oid: oid, Authenticated: true);
}
