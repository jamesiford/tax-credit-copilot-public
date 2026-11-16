using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Infrastructure.Ai.Telemetry;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class ResilienceTests
{
    [Fact]
    public async Task TransientRetryRecoveryAndOneBreakerFailurePerRequest()
    {
        var policy = new ResilienceSettings(RetryBase: TimeSpan.Zero);
        var inner = new ScriptRuntime("test", [new ModelException(ModelErrorKind.Unavailable, "offline")]);
        var stack = AiRegistration.BuildRuntime(inner, new InMemoryTokenBudget(), new Collector(), new() { Resilience = policy });
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(stack.StreamAsync(TestStreams.Request())));
        Assert.Equal(3, inner.Calls);
        var guarded = Assert.IsType<GuardedRuntime>(Assert.IsType<ObservedRuntime>(stack).Inner);
        var bulkhead = Assert.IsType<BulkheadRuntime>(guarded.Inner);
        var breaker = Assert.IsType<BreakerRuntime>(bulkhead.Inner);
        Assert.IsType<RetryRuntime>(breaker.Inner);
        Assert.IsType<TimeoutRuntime>(Assert.IsType<RetryRuntime>(breaker.Inner).Inner);
        Assert.Equal(CircuitState.Closed, breaker.Breaker.State);
        var recovering = new ScriptRuntime("test", [new ModelException(ModelErrorKind.Unavailable, "offline")], ["recovered"]);
        Assert.Equal("recovered", TestStreams.Text(await TestStreams.Collect(new RetryRuntime(recovering, policy).StreamAsync(TestStreams.Request()))));
    }
    [Theory]
    [InlineData(ModelErrorKind.Authentication)]
    [InlineData(ModelErrorKind.BadRequest)]
    [InlineData(ModelErrorKind.EgressRefused)]
    [InlineData(ModelErrorKind.BudgetExceeded)]
    public async Task ClientPolicyAndCredentialFailuresNeverRetry(ModelErrorKind kind)
    {
        var inner = new ScriptRuntime("test", [new ModelException(kind, "refused")]);
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(new RetryRuntime(inner,
            new ResilienceSettings(RetryBase: TimeSpan.Zero)).StreamAsync(TestStreams.Request())));
        Assert.Equal(1, inner.Calls);
    }
    [Fact]
    public async Task TextAndToolsPreventRetryAndProviderSwitch()
    {
        foreach (var first in new ModelEvent[] { new TextDelta("partial"), new ToolCall("synthetic", "lookup", "{}") })
        {
            var inner = new ScriptRuntime("one", [first, new ModelException(ModelErrorKind.Unavailable, "offline")]);
            var next = new ScriptRuntime("two", ["never"]);
            var retry = new RetryRuntime(inner, new(RetryBase: TimeSpan.Zero));
            await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(new ProviderChain([retry, next]).StreamAsync(TestStreams.Request())));
            Assert.Equal(1, inner.Calls);
            Assert.Equal(0, next.Calls);
        }
    }
    [Fact]
    public async Task RetryAfterBeyondDeadlineDoesNotSleepOrRetry()
    {
        var inner = new ScriptRuntime("test", [new ModelException(ModelErrorKind.RateLimited, "throttle", TimeSpan.FromMinutes(1))]);
        var runtime = new RetryRuntime(inner, new(Deadline: TimeSpan.FromMilliseconds(100)));
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(runtime.StreamAsync(TestStreams.Request())));
        Assert.Equal(1, inner.Calls);
    }
    [Fact]
    public async Task RetryAfterIsHonoredAndHealthyStreamsUseGapNotDuration()
    {
        var telemetry = new Collector();
        var inner = new ScriptRuntime("test", [new ModelException(ModelErrorKind.RateLimited, "throttle", TimeSpan.FromMilliseconds(5))], ["ok"]);
        var events = await TestStreams.Collect(new RetryRuntime(inner, new(), telemetry: telemetry).StreamAsync(TestStreams.Request()));
        Assert.Equal("ok", TestStreams.Text(events));
        Assert.Contains("ai.retries", telemetry.Counts);
        var healthy = new ScriptRuntime("test", [TimeSpan.FromMilliseconds(10), "a", TimeSpan.FromMilliseconds(10), "b"]);
        Assert.Equal("ab", TestStreams.Text(await TestStreams.Collect(new TimeoutRuntime(healthy, TimeSpan.FromMilliseconds(100)).StreamAsync(TestStreams.Request()))));
    }
    [Fact]
    public async Task FirstEventAndLaterGapTimeoutsAreTypedAndCancelUnderlying()
    {
        foreach (object[] script in new object[][] { [TimeSpan.FromMinutes(1)], ["partial", TimeSpan.FromMinutes(1)] })
        {
            var inner = new ScriptRuntime("test", script);
            var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(
                new TimeoutRuntime(inner, TimeSpan.FromMilliseconds(20)).StreamAsync(TestStreams.Request())));
            Assert.Equal(ModelErrorKind.Timeout, error.Kind);
        }
    }
    [Fact]
    public async Task TotalDeadlineIsTypedButCallerCancellationRemainsCancellation()
    {
        var inner = new ScriptRuntime("test", [TimeSpan.FromMinutes(1)]);
        var policy = new ResilienceSettings(RetryAttempts: 1, Deadline: TimeSpan.FromMilliseconds(20));
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(new RetryRuntime(inner, policy).StreamAsync(TestStreams.Request())));
        Assert.Equal("total_deadline", error.Code);
        using var stop = new CancellationTokenSource(TimeSpan.FromMilliseconds(20));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(
            new RetryRuntime(inner, new()).StreamAsync(TestStreams.Request(), stop.Token)));
    }
    [Fact]
    public async Task HalfOpenAllowsOneProbeAndCancelledProbeIsReleased()
    {
        var time = new FakeTime();
        var breaker = new CircuitBreaker(1, TimeSpan.FromSeconds(10), time);
        breaker.Failure();
        Assert.False(breaker.Allow());
        time.Advance(TimeSpan.FromSeconds(10));
        bool[] allowed = await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => Task.Run(breaker.Allow)));
        Assert.Single(allowed, v => v);
        breaker.ReleaseProbe();
        Assert.True(breaker.Allow());
        breaker.Success();
        Assert.Equal(CircuitState.Closed, breaker.State);
        breaker.Failure();
        time.Advance(TimeSpan.FromSeconds(10));
        Assert.True(breaker.Allow());
        breaker.Failure();
        Assert.Equal(CircuitState.Open, breaker.State);
        breaker.Reset();
        Assert.Equal(0, breaker.Opens);
    }
    [Fact]
    public async Task BulkheadShedsWithoutHealthPenaltyAndReleasesOnAbandonment()
    {
        var inner = new ScriptRuntime("test", ["first", TimeSpan.FromMinutes(1)]);
        var breaker = new CircuitBreaker(1, TimeSpan.FromSeconds(10));
        var bulkhead = new BulkheadRuntime(new BreakerRuntime(inner, breaker), 1);
        await using (var iterator = bulkhead.StreamAsync(TestStreams.Request()).GetAsyncEnumerator())
        {
            Assert.True(await iterator.MoveNextAsync());
            var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(bulkhead.StreamAsync(TestStreams.Request())));
            Assert.Equal(ModelErrorKind.BulkheadFull, error.Kind);
            Assert.False(error.Retryable);
            Assert.Equal(CircuitState.Closed, breaker.State);
            Assert.Equal(1, bulkhead.Active);
        }
        Assert.Equal(0, bulkhead.Active);
    }
}
