using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class BudgetTests
{
    [Fact]
    public async Task AtomicReservationsPreventConcurrentCheckRecordOverspend()
    {
        var budget = new InMemoryTokenBudget(10, 10);
        var reservations = await Task.WhenAll(Enumerable.Range(0, 30).Select(_ => Task.Run(() =>
        {
            try { return budget.Reserve("synthetic-user", 1); }
            catch (ModelException) { return null; }
        })));
        Assert.Equal(10, reservations.Count(r => r is not null));
        foreach (var reservation in reservations.OfType<ITokenReservation>())
        {
            reservation.RecordAttempt(new ModelUsage(1, 0));
            reservation.RecordAttempt(new ModelUsage(100, 100));
            reservation.Dispose();
        }
        Assert.Equal(10, budget.Used());
        Assert.Equal(10, budget.Used("synthetic-user"));
    }
    [Fact]
    public void UtcRolloverResetAndNoLimitAreExplicit()
    {
        var time = new FakeTime();
        var budget = new InMemoryTokenBudget(2, 2, time);
        using var reserved = budget.Reserve("synthetic-user", 2);
        reserved.RecordAttempt(new ModelUsage(2, 0));
        Assert.Throws<ModelException>(() => budget.Reserve("synthetic-user", 1));
        time.Advance(TimeSpan.FromDays(1));
        Assert.Equal(0, budget.Used());
        using var next = budget.Reserve("synthetic-user", 2);
        next.RecordAttempt(new ModelUsage(2, 0));
        budget.Reset();
        Assert.Equal(0, budget.Used());
        var unlimited = new InMemoryTokenBudget();
        using var large = unlimited.Reserve("synthetic-user", int.MaxValue);
        large.RecordAttempt(new ModelUsage(int.MaxValue, int.MaxValue));
        Assert.Equal(4294967294, unlimited.Used());
    }
    [Fact]
    public void AbandonedReservationReleasesAndPrincipalLimitsAreIndependent()
    {
        var budget = new InMemoryTokenBudget(10, 2);
        budget.Reserve("one", 2).Dispose();
        using var one = budget.Reserve("one", 2);
        using var two = budget.Reserve("two", 2);
        var error = Assert.Throws<ModelException>(() => budget.Reserve("one", 1));
        Assert.Equal("per_user_budget", error.Code);
        Assert.Equal(0, budget.Used());
    }
    [Theory]
    [InlineData("", 0)]
    [InlineData("x", 1)]
    [InlineData("1234", 1)]
    [InlineData("12345", 2)]
    public void EstimateRoundsUp(string text, int estimate) => Assert.Equal(estimate, InMemoryTokenBudget.EstimateTokens(text));
    [Fact]
    public async Task ReportedUsageReplacesEstimateAndRefusalPrecedesProviderCall()
    {
        var inner = new ScriptRuntime("test", [new ModelUsage(5, 3), "long text"]);
        var budget = new InMemoryTokenBudget(10, 10);
        var runtime = new AccountedRuntime(inner, budget);
        await TestStreams.Collect(runtime.StreamAsync(TestStreams.Request("1234")));
        Assert.Equal(8, budget.Used());
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(runtime.StreamAsync(TestStreams.Request("123456789"))));
        Assert.Equal(ModelErrorKind.BudgetExceeded, error.Kind);
        Assert.Equal(1, inner.Calls);
    }
    [Fact]
    public async Task FailedRetriesChargeEachPhysicalAttemptExactlyOnce()
    {
        var inner = new ScriptRuntime("test", [new ModelException(ModelErrorKind.Unavailable, "offline")], ["abcd"]);
        var budget = new InMemoryTokenBudget();
        var runtime = new RetryRuntime(new AccountedRuntime(inner, budget), new ResilienceSettings(RetryBase: TimeSpan.Zero));
        await TestStreams.Collect(runtime.StreamAsync(TestStreams.Request("abcd")));
        Assert.Equal(2, inner.Calls);
        Assert.Equal(3, budget.Used());
    }
    [Fact]
    public async Task EstimatedUsageIsExplicitAndPrecedesTerminalEvent()
    {
        var inner = new ScriptRuntime("test", ["abcd", new StreamEnd("test")]);
        var budget = new InMemoryTokenBudget();
        var events = await TestStreams.Collect(new AccountedRuntime(inner, budget).StreamAsync(TestStreams.Request("abcd")));
        Assert.Equal(new ModelUsage(1, 1, true), Assert.IsType<ModelUsage>(events[^2]));
        Assert.IsType<StreamEnd>(events[^1]);
        Assert.Equal(2, budget.Used());
    }
    [Fact]
    public async Task CancellationAndConsumerAbandonmentChargeOnlyStartedAttempt()
    {
        var budget = new InMemoryTokenBudget();
        var inner = new ScriptRuntime("test", ["abcd", TimeSpan.FromMinutes(1)]);
        var runtime = new AccountedRuntime(inner, budget);
        using var stop = new CancellationTokenSource();
        await using (var iterator = runtime.StreamAsync(TestStreams.Request("abcd"), stop.Token).GetAsyncEnumerator())
        {
            Assert.True(await iterator.MoveNextAsync());
            stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => iterator.MoveNextAsync().AsTask());
        }
        Assert.Equal(2, budget.Used());
        await using (var iterator = runtime.StreamAsync(TestStreams.Request("abcd")).GetAsyncEnumerator())
        {
            Assert.True(await iterator.MoveNextAsync());
        }

        Assert.Equal(4, budget.Used());
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(runtime.StreamAsync(TestStreams.Request(), cancelled.Token)));
        Assert.Equal(2, inner.Calls);
        Assert.Equal(4, budget.Used());
    }
}
