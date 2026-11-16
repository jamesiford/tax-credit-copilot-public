namespace TaxCredit.Orchestrator.Tests.Boundary;

internal sealed class DiagnosticClock : TimeProvider
{
    private readonly object sync = new();
    private readonly List<Timer> timers = [];
    private long ticks;

    public override long TimestampFrequency => TimeSpan.TicksPerSecond;
    public override long GetTimestamp() => Interlocked.Read(ref ticks);
    public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch.AddTicks(GetTimestamp());

    public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
    {
        var timer = new Timer(this, callback, state);
        timer.Change(dueTime, period);
        lock (sync)
        {
            timers.Add(timer);
        }
        return timer;
    }

    internal void Advance(TimeSpan amount, bool fireTimers = true)
    {
        Interlocked.Add(ref ticks, amount.Ticks);
        if (!fireTimers)
        {
            return;
        }
        Timer[] due;
        lock (sync)
        {
            due = timers.Where(timer => timer.Due <= GetTimestamp()).ToArray();
        }
        foreach (var timer in due)
        {
            timer.Fire();
        }
    }

    private sealed class Timer(DiagnosticClock clock, TimerCallback callback, object? state) : ITimer
    {
        private int disposed;
        internal long Due { get; private set; }
        public bool Change(TimeSpan dueTime, TimeSpan period)
        {
            Due = dueTime == Timeout.InfiniteTimeSpan ? long.MaxValue : clock.GetTimestamp() + dueTime.Ticks;
            return Volatile.Read(ref disposed) == 0;
        }
        internal void Fire()
        {
            if (Interlocked.Exchange(ref disposed, 1) == 0)
            {
                callback(state);
            }
        }
        public void Dispose() => Interlocked.Exchange(ref disposed, 1);
        public ValueTask DisposeAsync()
        {
            Dispose();
            return ValueTask.CompletedTask;
        }
    }
}
