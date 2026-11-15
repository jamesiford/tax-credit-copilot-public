using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Runs;

/// <summary>What a batch does for each client (Python <c>BatchKind</c>, a <c>str, Enum</c>).</summary>
public enum BatchKind
{
    /// <summary>Python <c>ASSESS</c> (<c>"assess"</c>).</summary>
    Assess,

    /// <summary>Python <c>CALCULATE</c> (<c>"calculate"</c>).</summary>
    Calculate,

    /// <summary>Python <c>ASSESS_AND_CALCULATE</c> (<c>"assess_and_calculate"</c>).</summary>
    AssessAndCalculate,
}

/// <summary>How the clients of a batch were chosen (Python <c>ScopeKind</c>).</summary>
public enum ScopeKind
{
    /// <summary>Python <c>ONE</c> (<c>"one"</c>).</summary>
    One,

    /// <summary>Python <c>LIST</c> (<c>"list"</c>).</summary>
    List,

    /// <summary>Python <c>FILTER</c> (<c>"filter"</c>).</summary>
    Filter,

    /// <summary>Python <c>ALL</c> (<c>"all"</c>).</summary>
    All,
}

/// <summary>Where a batch is, derived from its items (Python <c>BatchStatus</c>).</summary>
public enum BatchStatus
{
    /// <summary>Python <c>QUEUED</c> (<c>"queued"</c>).</summary>
    Queued,

    /// <summary>Python <c>RUNNING</c> (<c>"running"</c>).</summary>
    Running,

    /// <summary>Python <c>SUCCEEDED</c> (<c>"succeeded"</c>).</summary>
    Succeeded,

    /// <summary>Python <c>PARTIAL</c> (<c>"partial"</c>).</summary>
    Partial,

    /// <summary>Python <c>FAILED</c> (<c>"failed"</c>).</summary>
    Failed,

    /// <summary>Python <c>CANCELLED</c> (<c>"cancelled"</c>).</summary>
    Cancelled,
}

/// <summary>Where one item is in its life (Python <c>ItemStatus</c>). The declaration order is Python's iteration order.</summary>
public enum ItemStatus
{
    /// <summary>Python <c>QUEUED</c> (<c>"queued"</c>).</summary>
    Queued,

    /// <summary>Python <c>LEASED</c> (<c>"leased"</c>).</summary>
    Leased,

    /// <summary>Python <c>RUNNING</c> (<c>"running"</c>).</summary>
    Running,

    /// <summary>Python <c>SUCCEEDED</c> (<c>"succeeded"</c>).</summary>
    Succeeded,

    /// <summary>Python <c>SKIPPED_UNCHANGED</c> (<c>"skipped_unchanged"</c>).</summary>
    SkippedUnchanged,

    /// <summary>Python <c>SKIPPED_NO_PAYROLL</c> (<c>"skipped_no_payroll"</c>).</summary>
    SkippedNoPayroll,

    /// <summary>Python <c>FAILED</c> (<c>"failed"</c>).</summary>
    Failed,

    /// <summary>Python <c>CANCELLED</c> (<c>"cancelled"</c>).</summary>
    Cancelled,
}

/// <summary>The wire strings of the run enums and <c>Enum(value)</c> lookups (Python <c>domain/runs.py</c>).</summary>
public static class RunEnumExtensions
{
    private static readonly string[] BatchKinds = ["assess", "calculate", "assess_and_calculate"];
    private static readonly string[] ScopeKinds = ["one", "list", "filter", "all"];
    private static readonly string[] BatchStatuses = ["queued", "running", "succeeded", "partial", "failed", "cancelled"];
    private static readonly string[] ItemStatuses = ["queued", "leased", "running", "succeeded", "skipped_unchanged", "skipped_no_payroll", "failed", "cancelled"];

    /// <summary>Every item status in Python's declaration (iteration) order.</summary>
    public static IReadOnlyList<ItemStatus> AllItemStatuses { get; } = Enum.GetValues<ItemStatus>();

    /// <summary>Python <c>kind.value</c>.</summary>
    /// <param name="kind">The member.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this BatchKind kind) => BatchKinds[(int)kind];

    /// <summary>Python <c>scope.value</c>.</summary>
    /// <param name="scope">The member.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this ScopeKind scope) => ScopeKinds[(int)scope];

    /// <summary>Python <c>status.value</c>.</summary>
    /// <param name="status">The member.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this BatchStatus status) => BatchStatuses[(int)status];

    /// <summary>Python <c>status.value</c>.</summary>
    /// <param name="status">The member.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this ItemStatus status) => ItemStatuses[(int)status];

    /// <summary>Python <c>BatchKind(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The member.</returns>
    /// <exception cref="PyValueError">For a value that is not a member, with Python's message.</exception>
    public static BatchKind BatchKindFromValue(string value) => (BatchKind)Lookup(BatchKinds, value, "BatchKind");

    /// <summary>Python <c>ScopeKind(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The member.</returns>
    /// <exception cref="PyValueError">For a value that is not a member, with Python's message.</exception>
    public static ScopeKind ScopeKindFromValue(string value) => (ScopeKind)Lookup(ScopeKinds, value, "ScopeKind");

    /// <summary>Python <c>BatchStatus(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The member.</returns>
    /// <exception cref="PyValueError">For a value that is not a member, with Python's message.</exception>
    public static BatchStatus BatchStatusFromValue(string value) => (BatchStatus)Lookup(BatchStatuses, value, "BatchStatus");

    /// <summary>Python <c>ItemStatus(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The member.</returns>
    /// <exception cref="PyValueError">For a value that is not a member, with Python's message.</exception>
    public static ItemStatus ItemStatusFromValue(string value) => (ItemStatus)Lookup(ItemStatuses, value, "ItemStatus");

    // Python's message is "<repr(value)> is not a valid <Class>", so the quoting follows repr (a value holding a single quote is double-quoted).
    private static int Lookup(string[] values, string value, string type)
    {
        var index = Array.IndexOf(values, value);
        return index >= 0 ? index : throw new PyValueError($"{PyStr.Repr(value)} is not a valid {type}");
    }
}
