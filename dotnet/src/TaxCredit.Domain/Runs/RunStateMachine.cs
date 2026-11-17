using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Runs;

/// <summary>
/// An item or batch was asked to move somewhere the state machine does not allow (Python <c>IllegalTransition(ValueError)</c>).
/// </summary>
/// <param name="message">What was refused.</param>
public sealed class IllegalTransition(string message) : PyException("IllegalTransition", message);

/// <summary>The item state machine and the batch status derived from item counts (Python <c>domain/runs.py</c>). [ADR-012]</summary>
public static class RunStateMachine
{
    /// <summary>Items that will not change again unless somebody retries them (Python <c>TERMINAL_ITEMS</c>).</summary>
    public static IReadOnlySet<ItemStatus> TerminalItems { get; } = new HashSet<ItemStatus>
    {
        ItemStatus.Succeeded, ItemStatus.SkippedUnchanged, ItemStatus.SkippedNoPayroll, ItemStatus.Failed, ItemStatus.Cancelled,
    };

    /// <summary>Python <c>SKIPPED_ITEMS</c>.</summary>
    public static IReadOnlySet<ItemStatus> SkippedItems { get; } = new HashSet<ItemStatus> { ItemStatus.SkippedUnchanged, ItemStatus.SkippedNoPayroll };

    /// <summary>Python <c>ACTIVE_ITEMS</c>.</summary>
    public static IReadOnlySet<ItemStatus> ActiveItems { get; } = new HashSet<ItemStatus> { ItemStatus.Leased, ItemStatus.Running };

    /// <summary>
    /// Legal item moves (Python <c>_ITEM_MOVES</c>). <c>leased -&gt; queued</c> is a worker giving a claim back; <c>failed -&gt; queued</c> is an
    /// operator's retry; nothing leaves <c>succeeded</c>, a skip or <c>cancelled</c> (they have no entry, so every target is refused).
    /// </summary>
    public static IReadOnlyDictionary<ItemStatus, IReadOnlySet<ItemStatus>> ItemMoves { get; } = new Dictionary<ItemStatus, IReadOnlySet<ItemStatus>>
    {
        [ItemStatus.Queued] = new HashSet<ItemStatus> { ItemStatus.Leased, ItemStatus.Cancelled },
        [ItemStatus.Leased] = new HashSet<ItemStatus>
        {
            ItemStatus.Running, ItemStatus.Queued, ItemStatus.Cancelled, ItemStatus.SkippedUnchanged, ItemStatus.SkippedNoPayroll,
        },
        [ItemStatus.Running] = new HashSet<ItemStatus>
        {
            ItemStatus.Succeeded, ItemStatus.Failed, ItemStatus.Queued, ItemStatus.SkippedUnchanged, ItemStatus.SkippedNoPayroll,
        },
        [ItemStatus.Failed] = new HashSet<ItemStatus> { ItemStatus.Queued },
    };

    /// <summary>Python <c>check_item_move</c>: refuses any move the table does not list, including a move to the same status.</summary>
    /// <param name="current">Where the item is.</param>
    /// <param name="target">Where it is asked to go.</param>
    /// <exception cref="IllegalTransition">When the move is not allowed.</exception>
    public static void CheckItemMove(ItemStatus current, ItemStatus target)
    {
        if (!ItemMoves.TryGetValue(current, out var allowed) || !allowed.Contains(target))
        {
            throw new IllegalTransition($"an item cannot move from {current.Value()} to {target.Value()}");
        }
    }

    /// <summary>
    /// Python <c>batch_status</c>: the batch's status from its item counts (keyed by item status value). Counts are summed as Python ints, so
    /// a table with negative or unknown keys is judged by the same arithmetic (<c>if open_items:</c> is "non-zero", not "positive").
    /// </summary>
    /// <param name="counts">Items per status value; unknown keys count towards the total only.</param>
    /// <param name="cancelRequested">Whether cancel was requested (only read for an empty batch).</param>
    /// <returns>The derived status.</returns>
    public static BatchStatus BatchStatusOf(IReadOnlyDictionary<string, long> counts, bool cancelRequested = false)
    {
        ArgumentNullException.ThrowIfNull(counts);
        var total = Sum(counts.Values);
        if (total == 0)
        {
            return cancelRequested ? BatchStatus.Cancelled : BatchStatus.Succeeded;
        }

        var openItems = Sum(RunEnumExtensions.AllItemStatuses.Where(s => !TerminalItems.Contains(s)).Select(s => counts.GetValueOrDefault(s.Value())));
        if (openItems != 0)
        {
            var started = total - counts.GetValueOrDefault(ItemStatus.Queued.Value());
            return started != 0 ? BatchStatus.Running : BatchStatus.Queued;
        }

        return FinishedStatus(counts, total);
    }

    // The status of a batch with no open items left (Python _finished_status).
    private static BatchStatus FinishedStatus(IReadOnlyDictionary<string, long> counts, long total)
    {
        var failed = counts.GetValueOrDefault(ItemStatus.Failed.Value());
        var cancelled = counts.GetValueOrDefault(ItemStatus.Cancelled.Value());
        if (failed == 0 && cancelled == 0)
        {
            return BatchStatus.Succeeded;
        }

        if (total - failed - cancelled == 0)
        {
            return failed == 0 ? BatchStatus.Cancelled : BatchStatus.Failed;
        }

        return BatchStatus.Partial;
    }

    // Python ints do not overflow; a table whose sum leaves 64 bits is outside the ported range.
    private static long Sum(IEnumerable<long> values)
    {
        try
        {
            return values.Aggregate(0L, (a, b) => checked(a + b));
        }
        catch (OverflowException)
        {
            throw new PyUnsupportedException("item counts beyond 64 bits");
        }
    }
}
