namespace TaxCredit.Application.Hosting;

/// <summary>The publication identity is allocated durably before computation and reused by the certified runner on retry.</summary>
public sealed class RunIdentityScope
{
    private readonly AsyncLocal<string?> _current = new();
    /// <summary>Null outside a durable queue publication.</summary>
    public string? Current => _current.Value;
    /// <summary>The caller pushes synchronously in the execution context invoking the calculation.</summary>
    public IDisposable Push(string runId)
    {
        var old = _current.Value;
        _current.Value = runId;
        return new Restore(() => _current.Value = old);
    }

    private sealed class Restore(Action restore) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) { return; }
            _disposed = true;
            restore();
        }
    }
}
