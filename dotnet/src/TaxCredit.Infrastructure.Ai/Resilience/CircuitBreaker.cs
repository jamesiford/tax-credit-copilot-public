namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>The provider breaker state machine.</summary>
public enum CircuitState
{
    /// <summary>Requests are admitted.</summary>
    Closed,
    /// <summary>Requests are refused until reset.</summary>
    Open,
    /// <summary>Exactly one recovery probe is admitted.</summary>
    HalfOpen
}

/// <summary>A lock makes half-open a single probe even when multiple requests arrive concurrently.</summary>
public sealed class CircuitBreaker(int failureThreshold, TimeSpan resetAfter, TimeProvider? clock = null)
{
    private readonly Lock _sync = new();
    private readonly TimeProvider _clock = clock ?? TimeProvider.System;
    private CircuitState _state;
    private int _failures;
    private long _openedAt;
    private bool _probe;
    /// <summary>Number of state transitions into open.</summary>
    public int Opens { get; private set; }
    /// <summary>Current state after applying the monotonic reset interval.</summary>
    public CircuitState State { get { lock (_sync) { Roll(); return _state; } } }
    /// <summary>Atomically admits normal traffic or claims the single recovery probe.</summary>
    public bool Allow()
    {
        lock (_sync)
        {
            Roll();
            if (_state == CircuitState.Closed)
            {
                return true;
            }

            if (_state == CircuitState.HalfOpen && !_probe) { _probe = true; return true; }
            return false;
        }
    }
    /// <summary>Clears consecutive failures after a completed request.</summary>
    public void Success() { lock (_sync) { _state = CircuitState.Closed; _failures = 0; _probe = false; } }
    /// <summary>Records one failed logical request, not each retry attempt.</summary>
    public void Failure()
    {
        lock (_sync)
        {
            if (++_failures < failureThreshold && _state != CircuitState.HalfOpen)
            {
                return;
            }

            if (_state != CircuitState.Open)
            {
                Opens++;
            }

            _state = CircuitState.Open;
            _openedAt = _clock.GetTimestamp();
            _probe = false;
        }
    }
    /// <summary>Releases a cancelled, abandoned or policy-refused probe without a health penalty.</summary>
    public void ReleaseProbe() { lock (_sync) { _probe = false; } }
    /// <summary>Clears health state between isolated harness scenarios.</summary>
    public void Reset() { lock (_sync) { Success(); Opens = 0; } }
    private void Roll()
    {
        if (_state == CircuitState.Open && _clock.GetElapsedTime(_openedAt) >= resetAfter)
        { _state = CircuitState.HalfOpen; _probe = false; }
    }
}
