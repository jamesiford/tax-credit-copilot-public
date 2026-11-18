using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Warehouse;

/// <summary>
/// One human adjustment, as <c>ops.manual_override</c> records it (Python <c>ManualOverride</c>, a frozen dataclass whose
/// <c>__post_init__</c> checks the scope). Additive and append-only: clearing a base year is a new row whose <see cref="ValueAfter"/> is
/// <c>null</c>, never a delete. See <see cref="RunManifest"/> for why <see cref="Replace"/> exists.
/// </summary>
public sealed record ManualOverride
{
    /// <summary>Validates the scope like Python's <c>__post_init__</c>.</summary>
    /// <param name="overrideId">The adjustment id.</param>
    /// <param name="runId">The run it adjusts.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="scope">One of <see cref="WarehouseVocabulary.OverrideScopes"/>.</param>
    /// <param name="targetKey">What is adjusted, for example <see cref="WarehouseVocabulary.BaseYearKey"/>.</param>
    /// <param name="fieldChanged">The field changed.</param>
    /// <param name="valueBefore">The value before.</param>
    /// <param name="valueAfter">The value after; <c>null</c> clears it.</param>
    /// <param name="reasonCode">A coded reason.</param>
    /// <param name="justificationText">The free-text justification.</param>
    /// <param name="createdBy">Who made it.</param>
    /// <param name="createdAt">When it was made.</param>
    /// <param name="approvedBy">Who approved it.</param>
    /// <param name="approvedAt">When it was approved.</param>
    /// <exception cref="PyValueError">When the scope is not recognised.</exception>
    public ManualOverride(
        string overrideId,
        string runId,
        long clientId,
        string scope,
        string targetKey,
        string fieldChanged,
        string? valueBefore,
        string? valueAfter,
        string? reasonCode,
        string? justificationText,
        string createdBy,
        PyDateTime createdAt,
        string? approvedBy = null,
        PyDateTime? approvedAt = null)
    {
        OverrideId = overrideId;
        RunId = runId;
        ClientId = clientId;
        Scope = scope;
        TargetKey = targetKey;
        FieldChanged = fieldChanged;
        ValueBefore = valueBefore;
        ValueAfter = valueAfter;
        ReasonCode = reasonCode;
        JustificationText = justificationText;
        CreatedBy = createdBy;
        CreatedAt = createdAt;
        ApprovedBy = approvedBy;
        ApprovedAt = approvedAt;
        Validate();
    }

    /// <summary>The adjustment id.</summary>
    public string OverrideId { get; init; }

    /// <summary>The run it adjusts.</summary>
    public string RunId { get; init; }

    /// <summary>The client.</summary>
    public long ClientId { get; init; }

    /// <summary>The scope.</summary>
    public string Scope { get; init; }

    /// <summary>What is adjusted.</summary>
    public string TargetKey { get; init; }

    /// <summary>The field changed.</summary>
    public string FieldChanged { get; init; }

    /// <summary>The value before.</summary>
    public string? ValueBefore { get; init; }

    /// <summary>The value after; <c>null</c> means the choice was cleared.</summary>
    public string? ValueAfter { get; init; }

    /// <summary>A coded reason.</summary>
    public string? ReasonCode { get; init; }

    /// <summary>The free-text justification.</summary>
    public string? JustificationText { get; init; }

    /// <summary>Who made it.</summary>
    public string CreatedBy { get; init; }

    /// <summary>When it was made.</summary>
    public PyDateTime CreatedAt { get; init; }

    /// <summary>Who approved it.</summary>
    public string? ApprovedBy { get; init; }

    /// <summary>When it was approved.</summary>
    public PyDateTime? ApprovedAt { get; init; }

    /// <summary>Python <c>dataclasses.replace</c>: applies <paramref name="change"/> (a <c>with</c> expression) and re-validates.</summary>
    /// <param name="change">The edit.</param>
    /// <returns>The validated copy.</returns>
    /// <exception cref="PyValueError">When the edited adjustment is invalid.</exception>
    public ManualOverride Replace(Func<ManualOverride, ManualOverride> change)
    {
        ArgumentNullException.ThrowIfNull(change);
        var copy = change(this);
        copy.Validate();
        return copy;
    }

    private void Validate()
    {
        if (!WarehouseVocabulary.OverrideScopes.Contains(Scope))
        {
            throw new PyValueError($"scope must be one of {WarehouseVocabulary.SortedRepr(WarehouseVocabulary.OverrideScopes)}, got {PyStr.Repr(Scope)}");
        }
    }
}

/// <summary>Where human adjustments are recorded (Python <c>ManualOverrideRepository</c> Protocol); append-only.</summary>
public interface IManualOverrideRepository
{
    /// <summary>Whether adjustments survive a restart (a Protocol attribute in Python).</summary>
    bool IsDurable { get; }

    /// <summary>Appends one adjustment.</summary>
    /// <param name="overrideRow">The adjustment.</param>
    /// <returns>What was stored.</returns>
    ManualOverride Record(ManualOverride overrideRow);

    /// <summary>The base year currently chosen per location; the latest row wins and a row whose value after is <c>null</c> means the choice was cleared.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The program code.</param>
    /// <returns>Location key to base year.</returns>
    IReadOnlyDictionary<string, long> BaseYears(long clientId, string programCode);

    /// <summary>Every adjustment for a client, oldest first.</summary>
    /// <param name="clientId">The client.</param>
    /// <returns>The adjustments.</returns>
    IReadOnlyList<ManualOverride> History(long clientId);
}
