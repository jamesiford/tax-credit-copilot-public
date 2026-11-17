using TaxCredit.Application.Hosting;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Worker;

/// <summary>Bounded polling prevents an idle host or unavailable store from spinning; shutdown refunds untouched leases.</summary>
public sealed class QueueWorker(RunWorkExecutor executor, RunWorkGate gate, RuntimeStatus status, ILogger<QueueWorker> logger) : BackgroundService
{
    private static readonly Action<ILogger, string, Exception?> Failed = LoggerMessage.Define<string>(LogLevel.Error,
        new EventId(10, "QueueFailure"), "Queue execution stopped this poll ({FailureType}).");

    /// <inheritdoc />
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        status.Settle();
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var lease = await gate.Enter(stoppingToken).ConfigureAwait(false);
                await executor.Drain(stoppingToken, maximumItems: 1).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception error) when (error is System.Data.Common.DbException or AmbiguousCommitException or Application.Ports.Persistence.RunLeaseLost)
            {
                Failed(logger, error.GetType().Name, null);
            }
            await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken).ConfigureAwait(false);
        }
    }
}
