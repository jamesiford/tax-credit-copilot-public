using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Execution-context isolation lets a mediator read the caller without web dependencies.</summary>
public sealed class ApiPrincipalAccessor : IApiPrincipalAccessor
{
    private readonly AsyncLocal<ApiPrincipal?> _current = new();
    /// <inheritdoc />
    public ApiPrincipal? Current => _current.Value;
    /// <inheritdoc />
    public IDisposable Push(ApiPrincipal? principal)
    {
        var previous = _current.Value;
        _current.Value = principal;
        return new Restore(this, previous);
    }

    private sealed class Restore(ApiPrincipalAccessor owner, ApiPrincipal? previous) : IDisposable
    {
        private bool _disposed;
        public void Dispose()
        {
            if (_disposed) { return; }
            owner._current.Value = previous;
            _disposed = true;
        }
    }
}
