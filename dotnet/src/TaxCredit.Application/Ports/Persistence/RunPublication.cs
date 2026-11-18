using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Publication and terminal queue state must commit together, with a durable identity for crash reconciliation.</summary>
public interface IRunPublication
{
    /// <summary>Allocates once under the live tenant/owner lease, independently of a later failed calculation.</summary>
    string Identity(RunBatchItem item, string owner, PyDateTime now, Func<string> newId);
    /// <summary>False when the store has one writer, so a renewal cannot land while the write transaction runs (SQLite).</summary>
    bool RenewalsReachTheQueue { get; }
    /// <summary>Runs the delegate only when its accepted manifest is absent, rechecks ownership, then atomically finishes.</summary>
    /// <remarks>
    /// With a <paramref name="lease" /> the calculation and Gold write commit without touching the queue row, so the lease can be renewed on its own connection
    /// for as long as they run; the lease is verified immediately before that commit and the completion then commits in a short transaction of its own. A crash
    /// between the two is reconciled by the durable run identity and the accepted manifest, exactly as for an ambiguous acknowledgement.
    /// </remarks>
    void Publish(RunBatchItem item, string owner, string? runId, Func<ItemResult> calculate,
        Func<PyDateTime> now, CancellationToken cancellationToken, int leaseSeconds = 600, IRunLease? lease = null);
}

/// <summary>A queue lease that something else keeps renewing while an item runs, and which a long write consults before it commits.</summary>
public interface IRunLease
{
    /// <summary>Throws <see cref="RunLeaseLost" /> when a renewal found the lease gone or the last renewed expiry is too close to rely on.</summary>
    void ThrowIfLost();
    /// <summary>Makes <see cref="ThrowIfLost" /> visible to code running on this execution flow (the Gold writer checks it between tables and batches).</summary>
    IDisposable Enter();
    /// <summary>Stops renewing and waits for an in-flight renewal, so the completion does not race it on the same queue row.</summary>
    void Quiesce();
}

/// <summary>Links a source freshness observation to its run without replacing the certified content identity.</summary>
public interface IRunSourceObservations
{
    /// <summary>Participates in the calculation's ambient transaction.</summary>
    void Record(long clientId, string runId, SourceFingerprint fingerprint);
    /// <summary>Returns the original observation; absence is unknown, not current.</summary>
    SourceFingerprint? Get(long clientId, string runId);
}

/// <summary>A lost lease rolls back publication instead of recording a successful duplicate.</summary>
public sealed class RunLeaseLost() : InvalidOperationException("The queue lease is no longer owned.");

/// <summary>Retry classification stays outside SDK-free orchestration.</summary>
public interface IRunFailureClassifier
{
    /// <summary>Returns safe dependency/code labels; raw exception messages never enter the queue.</summary>
    RunFailure Classify(Exception error);
    /// <summary>An unknown commit must be reconciled or left for recovery, never immediately replayed.</summary>
    bool IsAmbiguous(Exception error);
}

/// <summary>A bounded retry decision, not an upstream payload.</summary>
public sealed record RunFailure(bool Retry, string Dependency, string Code);
