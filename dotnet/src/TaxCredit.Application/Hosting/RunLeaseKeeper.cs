using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Hosting;

/// <summary>Lets code deep in a write (the Gold writer) stop at a safe boundary once the item's lease is gone, without a token being threaded through the Domain.</summary>
public static class RunLeaseScope
{
    private static readonly AsyncLocal<IRunLease?> Current = new();

    /// <summary>Throws <see cref="RunLeaseLost" /> when the lease of the item running on this flow is lost; does nothing outside an item.</summary>
    public static void ThrowIfLost() => Current.Value?.ThrowIfLost();

    internal static IDisposable Enter(IRunLease lease)
    {
        var previous = Current.Value;
        Current.Value = lease;
        return new Restore(previous);
    }

    private sealed class Restore(IRunLease? previous) : IDisposable
    {
        public void Dispose() => Current.Value = previous;
    }
}

/// <summary>
/// Renews one item's lease on a timer, on its own task and connection, for as long as the item runs. Renewal outcomes are fenced by time: the lease is
/// trusted only until the last successfully renewed expiry minus one renewal interval, and a claimant cannot take the item before that expiry.
/// </summary>
public sealed class RunLeaseKeeper : IRunLease, IDisposable
{
    private readonly IRunBatchRepository _queue;
    private readonly RunBatchItem _item;
    private readonly string _owner;
    private readonly TimeSpan _lease;
    private readonly TimeSpan _renew;
    private readonly IClock _clock;
    private readonly CancellationTokenSource _stop = new();
    private Task _loop = Task.CompletedTask;
    private long _expiryTicks;
    private readonly bool _fenceByClock;
    private int _lost;

    /// <summary>
    /// The caller has just heartbeated, so the lease runs for a full <paramref name="leaseSeconds" /> from now. A store whose renewals cannot land while the
    /// write transaction runs (SQLite has one writer) passes <paramref name="fenceByClock" /> false: nobody can claim the item during that write either, so only
    /// an explicit loss counts.
    /// </summary>
    public RunLeaseKeeper(IRunBatchRepository queue, RunBatchItem item, string owner, int leaseSeconds, int renewSeconds, IClock clock, bool fenceByClock = true)
    {
        ArgumentNullException.ThrowIfNull(queue);
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(clock);
        ArgumentOutOfRangeException.ThrowIfLessThan(renewSeconds, 1);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(leaseSeconds, renewSeconds);
        _queue = queue;
        _item = item;
        _owner = owner;
        _lease = TimeSpan.FromSeconds(leaseSeconds);
        _renew = TimeSpan.FromSeconds(renewSeconds);
        _clock = clock;
        _fenceByClock = fenceByClock;
        _expiryTicks = (clock.UtcNow + _lease).UtcTicks;
    }

    /// <summary>Begins renewing every renewal interval.</summary>
    public void Start() => _loop = Task.Run(Renew);

    private async Task Renew()
    {
        using var timer = new PeriodicTimer(_renew);
        try
        {
            while (await timer.WaitForNextTickAsync(_stop.Token).ConfigureAwait(false))
            {
                try
                {
                    var now = _clock.UtcNow;
                    if (!_queue.Heartbeat(_item.ClientId, _item.ItemId, _owner, (int)_lease.TotalSeconds, Instant(now)))
                    {
                        Interlocked.Exchange(ref _lost, 1);
                        return;
                    }

                    Interlocked.Exchange(ref _expiryTicks, (now + _lease).UtcTicks);
                }
                catch (Exception) when (!_stop.IsCancellationRequested)
                {
                    // A failed renewal is retried on the next tick; ThrowIfLost refuses once the last renewed expiry gets too close.
                }
            }
        }
        catch (OperationCanceledException) { }
    }

    /// <inheritdoc />
    public void ThrowIfLost()
    {
        if (Volatile.Read(ref _lost) == 1 || (_fenceByClock && _clock.UtcNow.UtcTicks >= Interlocked.Read(ref _expiryTicks) - _renew.Ticks))
        {
            throw new RunLeaseLost();
        }
    }

    /// <inheritdoc />
    public IDisposable Enter() => RunLeaseScope.Enter(this);

    /// <inheritdoc />
    public void Quiesce()
    {
        _stop.Cancel();
        _loop.GetAwaiter().GetResult();
    }

    /// <summary>Stops renewing.</summary>
    public void Dispose()
    {
        Quiesce();
        _stop.Dispose();
    }

    private static PyDateTime Instant(DateTimeOffset now) =>
        PyDateTime.FromIsoFormat(now.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'+00:00'", System.Globalization.CultureInfo.InvariantCulture));
}
