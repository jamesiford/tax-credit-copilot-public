using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Telemetry;

/// <summary>Observes refusal, success, error, caller cancellation and consumer abandonment outside every guard.</summary>
public sealed class ObservedRuntime(IAgentRuntime inner, IAiTelemetry telemetry) : RuntimeDecorator(inner)
{
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var span = telemetry.StartCall(new(request.Spec.Role, Name, request.Spec.Name));
        string outcome = "abandoned";
        string? errorType = null;
        ModelUsage? usage = null;
        StreamEnd? end = null;
        int chars = 0;
        try
        {
            await using var events = Inner.StreamAsync(request, cancellationToken).GetAsyncEnumerator(cancellationToken);
            while (true)
            {
                var (Moved, Error) = await NextAsync(events).ConfigureAwait(false);
                if (Error is { } error)
                {
                    outcome = error is OperationCanceledException && cancellationToken.IsCancellationRequested ? "cancelled" : "error";
                    errorType = error is ModelException model ? model.Kind.ToString() : "provider_error";
                    System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(error).Throw();
                }
                if (!Moved) { outcome = "ok"; break; }
                if (events.Current is ModelUsage measured)
                {
                    usage = measured;
                }

                if (events.Current is StreamEnd terminal)
                {
                    end = terminal;
                }

                if (events.Current is TextDelta text)
                {
                    chars += text.Text.Length;
                }

                yield return events.Current;
            }
        }
        finally { span.Finish(new(outcome, usage, errorType, end, request.Prompt.Length, chars)); }
    }
    private static async Task<(bool Moved, Exception? Error)> NextAsync(IAsyncEnumerator<ModelEvent> events)
    {
        try { return (await events.MoveNextAsync().ConfigureAwait(false), null); }
        catch (Exception error) { return (false, error); }
    }
}
