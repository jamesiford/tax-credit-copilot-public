using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.WorkspaceSealed;

/// <summary>The sealed artifact cannot be built from a client selector or synthetic payroll.</summary>
public sealed record GetWorkspaceAvailabilityQuery : IQuery<WorkspaceAvailability>;

/// <summary>The fixed missing-extract state; no reference inputs are read in this wave.</summary>
/// <param name="Available">False until the sealed success path is explicitly implemented.</param>
/// <param name="Workspace">Absent artifact represented by null, not a fabricated run.</param>
/// <param name="Reason">The missing input explanation.</param>
/// <param name="Remedy">What an operator can do instead.</param>
public sealed record WorkspaceAvailability(bool Available, object? Workspace, string Reason, string Remedy);

/// <summary>Returns unavailable rather than manufacturing a certified artifact.</summary>
public sealed class GetWorkspaceAvailabilityHandler : IRequestHandler<GetWorkspaceAvailabilityQuery, WorkspaceAvailability>
{
    /// <summary>The shared unavailable reason.</summary>
    public const string MissingInputs = "Reference workspace inputs missing: One.csv, Two.csv, Three.csv, Four.csv";

    /// <inheritdoc />
    public ValueTask<WorkspaceAvailability> Handle(GetWorkspaceAvailabilityQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(new WorkspaceAvailability(false, null, MissingInputs,
            "The certified reference run needs the reference client (account 1001) and its source; every other view reads the data that is present."));
}
