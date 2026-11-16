using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Settings changes replace immutable limiter snapshots, never mutate an active bucket's rate.</summary>
public sealed class RuntimeLimits(IRuntimeConfiguration settings, TimeProvider clock) : IApiRateLimiter
{
    private readonly object _lock = new();
    private ApiRateLimiter? _limiter;
    private string? _rate;

    /// <inheritdoc />
    public RateLimitDecision Check(string kind, ApiPrincipal principal)
    {
        lock (_lock)
        {
            var rate = settings.Get("RATE_LIMIT_PER_MINUTE");
            if (_limiter is null || rate != _rate)
            {
                _limiter = new ApiRateLimiter(ApiRateLimitOptions.Parse(rate), clock);
                _rate = rate;
            }
            return _limiter.Check(kind, principal);
        }
    }

    /// <inheritdoc />
    public void Reset()
    {
        lock (_lock) { _limiter = null; _rate = null; }
    }
}
