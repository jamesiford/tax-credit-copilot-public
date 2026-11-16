using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>One health decision around all retries of a logical provider request.</summary>
public sealed class BreakerRuntime(IAgentRuntime inner, CircuitBreaker breaker, IAiTelemetry? telemetry = null)
    : RuntimeDecorator(inner)
{
    /// <summary>The resettable health state for this provider.</summary>
    public CircuitBreaker Breaker { get; } = breaker;
    /// <inheritdoc/>
    public override ProviderStatus Status() => Breaker.State switch
    {
        CircuitState.Open => new(Name, ProviderState.Unavailable, "circuit_open"),
        CircuitState.HalfOpen => new(Name, ProviderState.Degraded, "circuit_half_open"),
        _ => Inner.Status()
    };
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!Breaker.Allow())
        {
            throw new ModelException(ModelErrorKind.CircuitOpen, "circuit_open");
        }

        bool completed = false;
        try
        {
            await using var events = Inner.StreamAsync(request, cancellationToken).GetAsyncEnumerator(cancellationToken);
            while (await NextAsync(events).ConfigureAwait(false))
            {
                yield return events.Current;
            }

            completed = true;
            Breaker.Success();
        }
        finally
        {
            if (!completed)
            {
                Breaker.ReleaseProbe();
            }
        }
    }
    private async Task<bool> NextAsync(IAsyncEnumerator<ModelEvent> events)
    {
        try { return await events.MoveNextAsync().ConfigureAwait(false); }
        catch (ModelException error) when (error.ProviderFailure)
        {
            int before = Breaker.Opens;
            Breaker.Failure();
            if (Breaker.Opens > before)
            {
                telemetry?.Count("ai.breaker_opens", provider: Name);
            }

            throw;
        }
    }
}
