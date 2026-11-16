using System.Globalization;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Hosting;

/// <summary>The Worker loop, finite mode and contract drain all call this bounded executor.</summary>
public sealed class RunWorkExecutor(IServiceScopeFactory scopes, IRunBatchRepository queue, IClock clock,
    IIdSource ids, IRunFailureClassifier failures, RunExecutionOptions options)
{
    /// <summary>Processes only work claimable now; future backoff is never advanced by a drain.</summary>
    public ValueTask<int> Drain(CancellationToken cancellationToken, int maximumItems = 1000)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(maximumItems, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(maximumItems, 10000);
        var count = 0;
        queue.ReapExpired(Now(), options.MaxAttempts);
        var owner = ids.NewId().ToString();
        while (count < maximumItems)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var item = queue.Claim(owner, 1, options.LeaseSeconds, Now()).SingleOrDefault();
            if (item is null) { break; }
            Execute(item, owner, cancellationToken);
            count++;
        }
        return ValueTask.FromResult(count);
    }

    private void Execute(RunBatchItem item, string owner, CancellationToken cancellationToken)
    {
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            using var scope = scopes.CreateScope();
            var services = scope.ServiceProvider;
            var publication = services.GetRequiredService<IRunPublication>();
            var operation = services.GetRequiredService<RunItemExecution>();
            var batch = queue.Get(item.BatchId) ?? throw new InvalidOperationException("The queue batch is missing.");
            if (!queue.Heartbeat(item.ClientId, item.ItemId, owner, options.LeaseSeconds, Now())) { throw new RunLeaseLost(); }
            if (!queue.MarkRunning(item.ClientId, item.ItemId, owner, item.TaxYear, item.ProgramCode, Now())) { throw new RunLeaseLost(); }
            var runId = batch.Kind == BatchKind.Assess ? null : publication.Identity(item, owner, Now(), () => ids.NewId().ToString("N"));
            publication.Publish(item, owner, runId,
                () => batch.Kind == BatchKind.Assess ? operation.Assess(item, batch)
                    : operation.Calculate(item, batch, operation.Resolve(item, batch), runId!), Now, cancellationToken, options.LeaseSeconds);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            queue.Release(item.ClientId, item.ItemId, owner, Now());
            queue.Refresh(item.BatchId, Now());
            throw;
        }
        catch (RunLeaseLost) { throw; }
        catch (ClientRunNotAvailable)
        {
            Finish(item, owner, new ItemResult { Status = ItemStatus.SkippedNoPayroll, SkipReason = "No runnable payroll year is available." });
        }
        catch (Exception error) when (!failures.IsAmbiguous(error))
        {
            var failure = failures.Classify(error);
            if (failure.Retry && item.Attempts < options.MaxAttempts)
            {
                var until = AddSeconds(clock.UtcNow, RetryPolicy.BackoffSeconds(item.Attempts, () => 0));
                if (!queue.Requeue(item.ClientId, item.ItemId, owner, Now(), until, failure.Dependency, failure.Code)) { throw new RunLeaseLost(); }
                queue.Refresh(item.BatchId, Now());
                return;
            }
            Finish(item, owner, new ItemResult { Status = ItemStatus.Failed, ErrorDependency = failure.Dependency, ErrorMessage = failure.Code });
        }
    }

    private void Finish(RunBatchItem item, string owner, ItemResult result)
    {
        if (!queue.Finish(item.ClientId, item.ItemId, owner, Now(), result, item.BatchId)) { throw new RunLeaseLost(); }
    }
    private PyDateTime Now() => Instant(clock.UtcNow);
    private static PyDateTime AddSeconds(DateTimeOffset now, double seconds) => Instant(now.AddSeconds(seconds));
    private static PyDateTime Instant(DateTimeOffset now) =>
        PyDateTime.FromIsoFormat(now.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'", CultureInfo.InvariantCulture));
}

/// <summary>The lease bounds a non-interruptible certified calculation; publication rechecks it before commit.</summary>
public sealed record RunExecutionOptions(int LeaseSeconds = 600, int MaxAttempts = 3);
