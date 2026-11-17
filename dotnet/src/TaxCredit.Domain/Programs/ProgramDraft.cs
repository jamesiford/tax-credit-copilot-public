using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// One proposal (Python <c>ProgramDraft</c>, a frozen dataclass). <see cref="Version"/> is the optimistic-concurrency token: a write names the version it read.
/// A draft has no runtime authority: nothing that calculates reads one. [ADR-005]
/// </summary>
/// <remarks>
/// Equality follows the generated <c>__eq__</c> (the three dict fields compare as dicts). Python's <c>hash()</c> always raises
/// <c>TypeError: unhashable type: 'dict'</c> (<c>years</c> is always a dict), so <see cref="HashableInPython"/> is <c>false</c> and
/// <see cref="GetHashCode"/> hashes the scalar fields rather than throwing. There is no validation: <c>replace</c> re-runs nothing.
/// </remarks>
public sealed record ProgramDraft
{
    /// <summary>The draft id.</summary>
    public required string DraftId { get; init; }

    /// <summary>The program code being proposed.</summary>
    public required string ProposedCode { get; init; }

    /// <summary>The program's name.</summary>
    public required string Name { get; init; }

    /// <summary>The jurisdiction level.</summary>
    public required string JurisdictionLevel { get; init; }

    /// <summary>The state, for a state program; <c>null</c> otherwise (Python has no default: it must be passed).</summary>
    public required string? State { get; init; }

    /// <summary>Where the draft is.</summary>
    public required DraftStatus Status { get; init; }

    /// <summary>The optimistic-concurrency token.</summary>
    public required long Version { get; init; }

    /// <summary>Who created it.</summary>
    public required string CreatedBy { get; init; }

    /// <summary>When it was created.</summary>
    public required PyDateTime CreatedAt { get; init; }

    /// <summary>Who last changed it.</summary>
    public required string UpdatedBy { get; init; }

    /// <summary>When it was last changed.</summary>
    public required PyDateTime UpdatedAt { get; init; }

    /// <summary>The base pack document.</summary>
    public PyDict? Pack { get; init; }

    /// <summary>The year pack documents by year; a fresh dict per instance.</summary>
    public PyDict Years { get; init; } = new();

    /// <summary>The last validation result.</summary>
    public PyDict? Validation { get; init; }

    /// <summary>Who asked for review.</summary>
    public string? ReviewRequestedBy { get; init; }

    /// <summary>The reviewer.</summary>
    public string? Reviewer { get; init; }

    /// <summary>The review decision.</summary>
    public string? Decision { get; init; }

    /// <summary>The reviewer's comment.</summary>
    public string? DecisionComment { get; init; }

    /// <summary>When it was decided.</summary>
    public PyDateTime? DecidedAt { get; init; }

    /// <summary>The documents hash the approval covers.</summary>
    public string? ApprovedSha256 { get; init; }

    /// <summary>When it was exported.</summary>
    public PyDateTime? ExportedAt { get; init; }

    /// <summary>The hash of what was exported.</summary>
    public string? ExportSha256 { get; init; }

    /// <summary>Python <c>content_sha256</c>: the hash of the canonical documents.</summary>
    public string ContentSha256 => ProgramDraftRules.DocumentsHash(Pack, Years);

    /// <summary>Whether Python's <c>hash()</c> would succeed: it never does (a dict is a field).</summary>
    public static bool HashableInPython => false;

    /// <summary>Python <c>with_changes</c> (<c>dataclasses.replace</c>): applies <paramref name="change"/> (a <c>with</c> expression); nothing is re-validated.</summary>
    /// <param name="change">The edit.</param>
    /// <returns>The edited copy.</returns>
    public ProgramDraft WithChanges(Func<ProgramDraft, ProgramDraft> change)
    {
        ArgumentNullException.ThrowIfNull(change);
        return change(this);
    }

    /// <inheritdoc />
    public bool Equals(ProgramDraft? other) =>
        other is not null
        && DraftId == other.DraftId && ProposedCode == other.ProposedCode && Name == other.Name && JurisdictionLevel == other.JurisdictionLevel
        && State == other.State && Status == other.Status && Version == other.Version && CreatedBy == other.CreatedBy
        && CreatedAt.Equals(other.CreatedAt) && UpdatedBy == other.UpdatedBy && UpdatedAt.Equals(other.UpdatedAt)
        && PyEquality.Equal(Pack, other.Pack) && PyEquality.Equal(Years, other.Years) && PyEquality.Equal(Validation, other.Validation)
        && ReviewRequestedBy == other.ReviewRequestedBy && Reviewer == other.Reviewer && Decision == other.Decision
        && DecisionComment == other.DecisionComment && Nullable.Equals(DecidedAt, other.DecidedAt) && ApprovedSha256 == other.ApprovedSha256
        && Nullable.Equals(ExportedAt, other.ExportedAt) && ExportSha256 == other.ExportSha256;

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(DraftId, ProposedCode, Name, Status, Version, CreatedBy, UpdatedBy);
}

/// <summary>One append-only audit row: who did what to which draft, and what it moved from and to (Python <c>DraftEvent</c>, a frozen dataclass).</summary>
/// <remarks>Equality compares <see cref="Detail"/> as a dict; Python's <c>hash()</c> always raises (see <see cref="ProgramDraft"/>).</remarks>
public sealed record DraftEvent
{
    /// <summary>The draft.</summary>
    public required string DraftId { get; init; }

    /// <summary>The sequence number within the draft.</summary>
    public required long Seq { get; init; }

    /// <summary>The kind of event, for example <c>created</c> or <c>approved</c>.</summary>
    public required string EventType { get; init; }

    /// <summary>Who did it.</summary>
    public required string Actor { get; init; }

    /// <summary>When.</summary>
    public required PyDateTime At { get; init; }

    /// <summary>The status it moved from (text, not an enum: the audit stores strings).</summary>
    public string? FromStatus { get; init; }

    /// <summary>The status it moved to.</summary>
    public string? ToStatus { get; init; }

    /// <summary>Further detail; a fresh dict per instance.</summary>
    public PyDict Detail { get; init; } = new();

    /// <summary>Whether Python's <c>hash()</c> would succeed: it never does (a dict is a field).</summary>
    public static bool HashableInPython => false;

    /// <inheritdoc />
    public bool Equals(DraftEvent? other) =>
        other is not null
        && DraftId == other.DraftId && Seq == other.Seq && EventType == other.EventType && Actor == other.Actor && At.Equals(other.At)
        && FromStatus == other.FromStatus && ToStatus == other.ToStatus && PyEquality.Equal(Detail, other.Detail);

    /// <inheritdoc />
    public override int GetHashCode() => HashCode.Combine(DraftId, Seq, EventType, Actor, At, FromStatus, ToStatus);
}

/// <summary>Where drafts live (Python <c>ProgramDraftRepository</c> Protocol; implementations are infrastructure). <c>Save</c> is conditional on the expected version; every save appends its events in the same transaction.</summary>
public interface IProgramDraftRepository
{
    /// <summary>Stores a new draft and its first event.</summary>
    /// <param name="draft">The draft.</param>
    /// <param name="draftEvent">The event to append.</param>
    void Create(ProgramDraft draft, DraftEvent draftEvent);

    /// <summary>Reads a draft.</summary>
    /// <param name="draftId">The id.</param>
    /// <returns>The draft, or <c>null</c> when there is none.</returns>
    ProgramDraft? Get(string draftId);

    /// <summary>Replaces the draft if it is still at <paramref name="expectedVersion"/>, else raises <see cref="DraftConflict"/>; appends the event.</summary>
    /// <param name="draft">The new state.</param>
    /// <param name="expectedVersion">The version the caller read.</param>
    /// <param name="draftEvent">The event to append.</param>
    /// <exception cref="DraftConflict">When the stored version has moved.</exception>
    void Save(ProgramDraft draft, long expectedVersion, DraftEvent draftEvent);

    /// <summary>Python <c>list_drafts</c>: a page of drafts and the total.</summary>
    /// <param name="status">A status to filter on, or <c>null</c> for every status.</param>
    /// <param name="limit">The page size (Python default 50).</param>
    /// <param name="offset">The page offset (Python default 0).</param>
    /// <returns>The page and the total count.</returns>
    (IReadOnlyList<ProgramDraft> Items, long Total) ListDrafts(string? status = null, long limit = 50, long offset = 0);

    /// <summary>A draft's events, oldest first.</summary>
    /// <param name="draftId">The id.</param>
    /// <returns>The events.</returns>
    IReadOnlyList<DraftEvent> Events(string draftId);

    /// <summary>A draft for the code that is neither withdrawn nor exported, if any.</summary>
    /// <param name="proposedCode">The code.</param>
    /// <returns>The live draft, or <c>null</c>.</returns>
    ProgramDraft? LiveForCode(string proposedCode);
}
