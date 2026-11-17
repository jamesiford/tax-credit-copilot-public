using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>Where a draft is (Python <c>DraftStatus</c>, a <c>str, Enum</c>). <see cref="Validating"/> is reserved for an asynchronous validator.</summary>
public enum DraftStatus
{
    /// <summary>Python <c>DRAFT</c> (<c>"draft"</c>).</summary>
    Draft,

    /// <summary>Python <c>VALIDATING</c> (<c>"validating"</c>).</summary>
    Validating,

    /// <summary>Python <c>NEEDS_CHANGES</c> (<c>"needs_changes"</c>).</summary>
    NeedsChanges,

    /// <summary>Python <c>READY_FOR_REVIEW</c> (<c>"ready_for_review"</c>).</summary>
    ReadyForReview,

    /// <summary>Python <c>APPROVED_FOR_EXPORT</c> (<c>"approved_for_export"</c>).</summary>
    ApprovedForExport,

    /// <summary>Python <c>EXPORTED</c> (<c>"exported"</c>).</summary>
    Exported,

    /// <summary>Python <c>WITHDRAWN</c> (<c>"withdrawn"</c>).</summary>
    Withdrawn,
}

/// <summary>The wire strings of <see cref="DraftStatus"/> and <c>DraftStatus(value)</c> (Python <c>domain/program_drafts.py</c>).</summary>
public static class DraftStatusExtensions
{
    private static readonly string[] Values = ["draft", "validating", "needs_changes", "ready_for_review", "approved_for_export", "exported", "withdrawn"];

    /// <summary>Statuses in which the documents may still be edited (Python <c>EDITABLE</c>): editing a draft under review would change what was reviewed.</summary>
    public static IReadOnlySet<DraftStatus> Editable { get; } = new HashSet<DraftStatus> { DraftStatus.Draft, DraftStatus.NeedsChanges };

    /// <summary>Statuses that end a draft's life (Python <c>CLOSED</c>); an exported draft can still be re-exported, byte for byte.</summary>
    public static IReadOnlySet<DraftStatus> Closed { get; } = new HashSet<DraftStatus> { DraftStatus.Withdrawn };

    /// <summary>Python <c>status.value</c>.</summary>
    /// <param name="status">The member.</param>
    /// <returns>The wire string.</returns>
    public static string Value(this DraftStatus status) => Values[(int)status];

    /// <summary>Python <c>DraftStatus(value)</c>.</summary>
    /// <param name="value">The wire string.</param>
    /// <returns>The member.</returns>
    /// <exception cref="PyValueError">For a value that is not a member, with Python's message.</exception>
    public static DraftStatus FromValue(string value)
    {
        var index = Array.IndexOf(Values, value);
        return index >= 0 ? (DraftStatus)index : throw new PyValueError($"{PyStr.Repr(value)} is not a valid DraftStatus");
    }
}
