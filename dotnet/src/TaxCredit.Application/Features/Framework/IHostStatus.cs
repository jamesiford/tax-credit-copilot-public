namespace TaxCredit.Application.Features.Framework;

/// <summary>Readiness and provider checks are captured at startup, not performed on a probe request.</summary>
public interface IHostStatus
{
    /// <summary>Liveness and configured provider state.</summary>
    IReadOnlyDictionary<string, object?> Health { get; }

    /// <summary>Settled startup checks; unavailable adapters must not claim readiness.</summary>
    IReadOnlyDictionary<string, object?> Readiness { get; }
}
