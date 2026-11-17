using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Application.Features.Ai.Streams;

internal static class ModelStream
{
    internal static IAsyncEnumerator<ModelEvent>? Open(Func<IAsyncEnumerable<ModelEvent>> stream,
        IAiTelemetry telemetry, CancellationToken cancellationToken)
    {
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            return stream().GetAsyncEnumerator(cancellationToken);
        }
#pragma warning disable CA1031 // A synchronous provider factory failure has the same safe fallback as a streamed failure.
        catch (Exception error) when (error is not OperationCanceledException)
        {
            telemetry.Count("ai.narration_failed", scope: error.GetType().Name);
            return null;
        }
#pragma warning restore CA1031
    }

    internal static async ValueTask<(bool HasValue, bool Failed)> MoveAsync(
        IAsyncEnumerator<ModelEvent> events, IAiTelemetry telemetry, CancellationToken cancellationToken)
    {
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            return (await events.MoveNextAsync().ConfigureAwait(false), false);
        }
#pragma warning disable CA1031 // The page receives explicit fallback; provider diagnostics contain no prompt or response text.
        catch (Exception error) when (error is not OperationCanceledException)
        {
            telemetry.Count("ai.narration_failed", scope: error.GetType().Name);
            return (false, true);
        }
#pragma warning restore CA1031
    }
}
