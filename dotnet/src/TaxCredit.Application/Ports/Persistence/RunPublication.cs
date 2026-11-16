using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Publication and terminal queue state must commit together, with a durable identity for crash reconciliation.</summary>
public interface IRunPublication
{
    /// <summary>Allocates once under the live tenant/owner lease, independently of a later failed calculation.</summary>
    string Identity(RunBatchItem item, string owner, PyDateTime now, Func<string> newId);
    /// <summary>Runs the delegate only when its accepted manifest is absent, rechecks ownership, then atomically finishes.</summary>
    void Publish(RunBatchItem item, string owner, string? runId, Func<ItemResult> calculate,
        Func<PyDateTime> now, CancellationToken cancellationToken, int leaseSeconds = 600);
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
