using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Only classified source outages and known aborted write conflicts consume a delayed retry budget.</summary>
public sealed class RunFailureClassifier : IRunFailureClassifier
{
    /// <inheritdoc />
    public RunFailure Classify(Exception error) => error switch
    {
        SourceUnavailable => new(true, "source", "source_unavailable"),
        SourceFailureException source => new(false, source.Dependency, source.Code),
        _ when SqlConflicts.IsAbortedConflict(error) => new(true, "persistence", "write_conflict"),
        _ => new(false, "calculation", error.GetType().Name),
    };

    /// <inheritdoc />
    public bool IsAmbiguous(Exception error) => error is AmbiguousCommitException;
}
