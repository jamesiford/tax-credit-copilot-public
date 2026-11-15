using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Runs;

/// <summary>One client (and maybe one year) in a batch (Python <c>RunBatchItem</c>, a frozen dataclass). All fields are scalars, so it is hashable.</summary>
public sealed record RunBatchItem
{
    /// <summary>The item id.</summary>
    public required string ItemId { get; init; }

    /// <summary>The batch it belongs to.</summary>
    public required string BatchId { get; init; }

    /// <summary>The client.</summary>
    public required long ClientId { get; init; }

    /// <summary>The position in the batch.</summary>
    public long Seq { get; init; }

    /// <summary>The programme, when the batch named one.</summary>
    public string? ProgramCode { get; init; }

    /// <summary>The tax year; <c>null</c> means the client's latest runnable year, resolved when the item starts.</summary>
    public long? TaxYear { get; init; }

    /// <summary>Where the item is.</summary>
    public ItemStatus Status { get; init; } = ItemStatus.Queued;

    /// <summary>How many times it has been tried.</summary>
    public long Attempts { get; init; }

    /// <summary>The worker holding the lease.</summary>
    public string? LeaseOwner { get; init; }

    /// <summary>When the lease lapses.</summary>
    public PyDateTime? LeaseExpiresAt { get; init; }

    /// <summary>The last heartbeat.</summary>
    public PyDateTime? HeartbeatAt { get; init; }

    /// <summary>Not to be claimed before this instant (a retry's backoff).</summary>
    public PyDateTime? NotBefore { get; init; }

    /// <summary>The run it produced.</summary>
    public string? RunId { get; init; }

    /// <summary>Why it was skipped.</summary>
    public string? SkipReason { get; init; }

    /// <summary>Which dependency failed.</summary>
    public string? ErrorDependency { get; init; }

    /// <summary>The error text.</summary>
    public string? ErrorMessage { get; init; }

    /// <summary>When it started.</summary>
    public PyDateTime? StartedAt { get; init; }

    /// <summary>When it finished.</summary>
    public PyDateTime? FinishedAt { get; init; }

    /// <summary>
    /// Python <c>moved</c>: checks the move against the state machine, then <c>dataclasses.replace</c>s the status and any other fields.
    /// </summary>
    /// <remarks>Python's <c>**changes</c> become a <paramref name="changes"/> edit of the copy; it must not set <see cref="Status"/> (Python raises <c>TypeError</c> for a duplicate keyword).</remarks>
    /// <param name="status">The status to move to.</param>
    /// <param name="changes">Further field changes applied to the moved copy, or <c>null</c>.</param>
    /// <returns>The moved copy.</returns>
    /// <exception cref="IllegalTransition">When the move is not allowed; nothing is changed.</exception>
    public RunBatchItem Moved(ItemStatus status, Func<RunBatchItem, RunBatchItem>? changes = null)
    {
        RunStateMachine.CheckItemMove(Status, status);
        var moved = this with { Status = status };
        return changes is null ? moved : changes(moved);
    }
}

/// <summary>How an item ended, as the queue records it (Python <c>ItemResult</c>, a frozen dataclass).</summary>
public sealed record ItemResult
{
    /// <summary>The final status.</summary>
    public required ItemStatus Status { get; init; }

    /// <summary>The run it produced.</summary>
    public string? RunId { get; init; }

    /// <summary>Why it was skipped.</summary>
    public string? SkipReason { get; init; }

    /// <summary>Which dependency failed.</summary>
    public string? ErrorDependency { get; init; }

    /// <summary>The error text.</summary>
    public string? ErrorMessage { get; init; }

    /// <summary>The tax year the item resolved to.</summary>
    public long? TaxYear { get; init; }
}
