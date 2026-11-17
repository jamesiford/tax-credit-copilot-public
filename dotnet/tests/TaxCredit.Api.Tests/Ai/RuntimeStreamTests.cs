using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Api.Tests.Ai;

public sealed class RuntimeStreamTests
{
    [Fact]
    public async Task Visible_upstream_failure_is_not_retried_and_closes_reservations_and_spans()
    {
        var first = new ScriptedRuntime("scripted");
        var spare = new ScriptedRuntime("spare");
        var budget = new TrackingBudget();
        var telemetry = new TrackingTelemetry();
        var registry = new ProviderRegistry();
        registry.Register(first.Name, () => first);
        registry.Register(spare.Name, () => spare);
        var options = new AiRuntimeOptions { Resilience = new ResilienceSettings(RetryBase: TimeSpan.Zero) };
        var router = new ModelRouter(registry, Enum.GetValues<ModelRole>().ToDictionary(role => role,
            _ => (IReadOnlyList<string>)["scripted", "spare"]),
            provider => AiRegistration.BuildRuntime(provider, budget, telemetry, options));
        await using var host = await AiSocketHost.Start(configure: services => services.AddSingleton(router));
        using var response = await host.Client.PostAsJsonAsync("/api/summary", new { page = "portfolio" });
        var frames = StreamEndpointTests.Parse(await response.Content.ReadAsStringAsync());
        Assert.Single(frames, frame => frame.Name == "token");
        Assert.Single(frames, frame => frame.Name == "fallback");
        Assert.Single(frames, frame => frame.Name == "done");
        Assert.Equal(1, first.Calls);
        Assert.Equal(0, spare.Calls);
        Assert.True(first.Disposed);
        Assert.Equal(0, budget.Active);
        Assert.True(budget.Used() > 0);
        Assert.Equal(0, telemetry.Active);
        await host.ScopeDisposed.WaitAsync(TimeSpan.FromSeconds(5));
    }

    private sealed class ScriptedRuntime(string name) : IAgentRuntime
    {
        internal int Calls { get; private set; }
        internal bool Disposed { get; private set; }
        public string Name => name;
        public bool ReadyFor(string agentName) => true;
        public string? VersionOf(string agentName) => "synthetic";
        public ProviderStatus Status() => new(Name, ProviderState.Ready);
        public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            Calls++;
            try
            {
                await Task.Yield();
                cancellationToken.ThrowIfCancellationRequested();
                yield return new TextDelta("A trusted reading.");
                throw new ModelException(ModelErrorKind.Unavailable, "synthetic_failure");
            }
            finally { Disposed = true; }
        }
    }

    private sealed class TrackingBudget : ITokenBudget
    {
        private readonly InMemoryTokenBudget _inner = new();
        internal int Active { get; private set; }
        public ITokenReservation Reserve(string principal, int estimatedTokens)
        {
            Active++;
            return new Reservation(this, _inner.Reserve(principal, estimatedTokens));
        }
        public long Used(string? principal = null) => _inner.Used(principal);
        public void Reset() => _inner.Reset();
        private sealed class Reservation(TrackingBudget owner, ITokenReservation inner) : ITokenReservation
        {
            public void RecordAttempt(ModelUsage usage) => inner.RecordAttempt(usage);
            public void Dispose() { inner.Dispose(); owner.Active--; }
        }
    }

    private sealed class TrackingTelemetry : IAiTelemetry
    {
        internal int Active { get; private set; }
        public IAiCallSpan StartCall(AiCallInfo info) { Active++; return new Span(this); }
        public void Count(string metric, long value = 1, string? provider = null, string? scope = null) { }
        private sealed class Span(TrackingTelemetry owner) : IAiCallSpan
        {
            public void Finish(AiCallResult result) => owner.Active--;
        }
    }
}
