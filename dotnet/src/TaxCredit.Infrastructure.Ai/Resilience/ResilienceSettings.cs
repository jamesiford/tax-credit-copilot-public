using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Resilience;

/// <summary>Bounded runtime policy, independent of transport SDK.</summary>
public sealed record ResilienceSettings(int RetryAttempts = 3, int MaxConcurrency = 8,
    int FailureThreshold = 5, TimeSpan? EventGap = null, TimeSpan? Deadline = null,
    TimeSpan? ResetAfter = null, TimeSpan? RetryBase = null)
{
    /// <summary>Maximum silence between events, including the first.</summary>
    public TimeSpan Gap => EventGap ?? TimeSpan.FromSeconds(30);
    /// <summary>The total deadline spanning attempts and backoff.</summary>
    public TimeSpan TotalDeadline => Deadline ?? TimeSpan.FromSeconds(45);
    /// <summary>The interval before a single half-open probe.</summary>
    public TimeSpan BreakerReset => ResetAfter ?? TimeSpan.FromSeconds(30);
    /// <summary>The base of capped full-jitter exponential backoff.</summary>
    public TimeSpan BaseDelay => RetryBase ?? TimeSpan.FromMilliseconds(500);
    /// <summary>The maximum exponential backoff ceiling, independent of explicit Retry-After.</summary>
    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromSeconds(8);
    /// <summary>Refuses invalid settings before constructing concurrency or timeout machinery.</summary>
    public void Validate()
    {
        if (RetryAttempts is < 1 or > 10 || MaxConcurrency < 1 || FailureThreshold < 1
            || Gap <= TimeSpan.Zero || TotalDeadline <= TimeSpan.Zero || BreakerReset <= TimeSpan.Zero
            || BaseDelay < TimeSpan.Zero || MaxDelay < TimeSpan.Zero
            || Gap.TotalMilliseconds > uint.MaxValue - 1 || TotalDeadline.TotalMilliseconds > uint.MaxValue - 1)
        {
            throw new ModelException(ModelErrorKind.Configuration, "invalid_resilience_settings");
        }
    }
}
