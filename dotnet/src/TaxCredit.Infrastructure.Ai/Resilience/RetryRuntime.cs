using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>Retries transient failures only before reader-visible output, within an overall deadline.</summary>
public sealed class RetryRuntime(IAgentRuntime inner, ResilienceSettings settings,
    TimeProvider? clock = null, Func<double>? jitter = null, IAiTelemetry? telemetry = null) : RuntimeDecorator(inner)
{
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var time = clock ?? TimeProvider.System;
        using var deadline = new CancellationTokenSource(settings.TotalDeadline, time);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, deadline.Token);
        long started = time.GetTimestamp();
        for (int attempt = 1; ; attempt++)
        {
            bool produced = false;
            await using var events = Inner.StreamAsync(request, linked.Token).GetAsyncEnumerator(linked.Token);
            ModelException? error;
            while (true)
            {
                var (Moved, Error) = await NextAsync(events, cancellationToken, deadline.Token).ConfigureAwait(false);
                error = Error;
                if (!Moved)
                {
                    break;
                }

                produced |= events.Current is TextDelta { Text.Length: > 0 } or ToolCall;
                yield return events.Current;
            }
            if (error is null)
            {
                yield break;
            }

            if (produced || !error.Retryable || attempt >= settings.RetryAttempts)
            {
                throw error;
            }

            var delay = error.RetryAfter ?? TimeSpan.FromSeconds(Math.Min(settings.MaxDelay.TotalSeconds,
                settings.BaseDelay.TotalSeconds * Math.Pow(2, attempt - 1)) * Math.Clamp((jitter ?? Random.Shared.NextDouble)(), 0, 1));
            if (time.GetElapsedTime(started) + delay >= settings.TotalDeadline)
            {
                throw error;
            }

            telemetry?.Count("ai.retries", provider: Name);
            await DelayAsync(delay, time, linked.Token, cancellationToken).ConfigureAwait(false);
        }
    }
    private static async Task<(bool Moved, ModelException? Error)> NextAsync(IAsyncEnumerator<ModelEvent> events,
        CancellationToken caller, CancellationToken deadline)
    {
        try { return (await events.MoveNextAsync().ConfigureAwait(false), null); }
        catch (OperationCanceledException) when (caller.IsCancellationRequested) { throw; }
        catch (OperationCanceledException) when (deadline.IsCancellationRequested)
        { return (false, new ModelException(ModelErrorKind.Timeout, "total_deadline")); }
        catch (ModelException error) { return (false, error); }
    }
    private static async Task DelayAsync(TimeSpan delay, TimeProvider time, CancellationToken linked, CancellationToken caller)
    {
        try { await Task.Delay(delay, time, linked).ConfigureAwait(false); }
        catch (OperationCanceledException) when (!caller.IsCancellationRequested)
        { throw new ModelException(ModelErrorKind.Timeout, "total_deadline"); }
    }
}
