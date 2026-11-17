using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Warehouse;

/// <summary>Run provenance constants (Python module constants in <c>domain/warehouse.py</c>).</summary>
public static class WarehouseVocabulary
{
    /// <summary>
    /// The <c>run_status</c> domain (Python <c>RUN_STATUSES</c>). The DDL records it as constraint intent only, because Fabric Warehouse
    /// accepts <c>CHECK</c> syntactically and does not enforce it, so this set is the only place the values are policed.
    /// </summary>
    public static IReadOnlySet<string> RunStatuses { get; } = new HashSet<string>(["running", "success", "failed", "superseded"], StringComparer.Ordinal);

    /// <summary><c>tcc_ops.run_manifest</c> column order, the DDL's (Python <c>RUN_MANIFEST_COLUMNS</c>); not the order of the dataclass fields.</summary>
    public static IReadOnlyList<string> RunManifestColumns { get; } =
    [
        "run_id", "client_id", "entity_id", "program_code", "tax_year", "fiscal_year_begin", "fiscal_year_end", "source_snapshot_id",
        "step1_assumption_set_id", "step1_assumption_sha256", "onezero_assumption_set_id", "onezero_assumption_sha256", "rule_pack_version",
        "code_commit", "calculation_id", "run_started_at", "run_completed_at", "run_status", "superseded_by_run_id", "triggered_by",
    ];

    /// <summary><c>tcc_ops.manual_override.scope</c> values the DDL declares (Python <c>OVERRIDE_SCOPES</c>).</summary>
    public static IReadOnlySet<string> OverrideScopes { get; } = new HashSet<string>(["employee", "record", "unit"], StringComparer.Ordinal);

    /// <summary>Python <c>base_year_key</c>: the <c>target_key</c> for a location's base year, for example <c>GA_JTC:GA_GA-010</c>.</summary>
    /// <param name="programCode">The program code.</param>
    /// <param name="worksiteId">The worksite id.</param>
    /// <returns>The key.</returns>
    public static string BaseYearKey(string programCode, string worksiteId) => programCode + ":" + worksiteId;

    internal static string SortedRepr(IReadOnlySet<string> set) =>
        "[" + string.Join(", ", PySort.Sorted(set, s => s, PyStr.Comparer).Select(PyStr.Repr)) + "]";

    internal static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}

/// <summary>
/// One calculation run, as <c>tcc_ops.run_manifest</c> stores it (Python <c>RunManifest</c>, a frozen dataclass whose
/// <c>__post_init__</c> validates). Field names and nullability mirror the deployed DDL column for column.
/// </summary>
/// <remarks>
/// A <c>with</c> expression copies without validating (C# records cannot hook it), whereas <c>dataclasses.replace</c> re-runs
/// <c>__post_init__</c>; use <see cref="Replace"/> to change a field and get Python's behaviour. Equality compares
/// <see cref="PyDateTime"/> structurally, so two aware datetimes for one instant in different offsets differ here and are equal in Python.
/// </remarks>
public sealed record RunManifest
{
    /// <summary>Validates like Python's <c>__post_init__</c>: the status first, then the fiscal window.</summary>
    /// <param name="runId">The run id.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The program code.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="fiscalYearBegin">First day of the fiscal window.</param>
    /// <param name="fiscalYearEnd">Last day of the fiscal window; must be after the begin.</param>
    /// <param name="runStartedAt">When the run started.</param>
    /// <param name="runStatus">One of <see cref="WarehouseVocabulary.RunStatuses"/>.</param>
    /// <param name="entityId">The entity.</param>
    /// <param name="sourceSnapshotId">The payroll snapshot.</param>
    /// <param name="step1AssumptionSetId">The Step 1 assumption set.</param>
    /// <param name="step1AssumptionSha256">Its hash.</param>
    /// <param name="onezeroAssumptionSetId">The One/Zero assumption set.</param>
    /// <param name="onezeroAssumptionSha256">Its hash.</param>
    /// <param name="rulePackVersion">The rule pack applied.</param>
    /// <param name="codeCommit">The commit that executed the run.</param>
    /// <param name="calculationId">The calculation id.</param>
    /// <param name="runCompletedAt">When the run finished; <c>null</c> while running.</param>
    /// <param name="supersededByRunId">The run that replaced this one.</param>
    /// <param name="triggeredBy">Who or what started it.</param>
    /// <exception cref="PyValueError">When the status is not recognised or the window ends on or before it begins.</exception>
    public RunManifest(
        string runId,
        long clientId,
        string programCode,
        long taxYear,
        DateOnly fiscalYearBegin,
        DateOnly fiscalYearEnd,
        PyDateTime runStartedAt,
        string runStatus,
        long? entityId = null,
        string? sourceSnapshotId = null,
        string? step1AssumptionSetId = null,
        string? step1AssumptionSha256 = null,
        string? onezeroAssumptionSetId = null,
        string? onezeroAssumptionSha256 = null,
        string? rulePackVersion = null,
        string? codeCommit = null,
        string? calculationId = null,
        PyDateTime? runCompletedAt = null,
        string? supersededByRunId = null,
        string? triggeredBy = null)
    {
        RunId = runId;
        ClientId = clientId;
        ProgramCode = programCode;
        TaxYear = taxYear;
        FiscalYearBegin = fiscalYearBegin;
        FiscalYearEnd = fiscalYearEnd;
        RunStartedAt = runStartedAt;
        RunStatus = runStatus;
        EntityId = entityId;
        SourceSnapshotId = sourceSnapshotId;
        Step1AssumptionSetId = step1AssumptionSetId;
        Step1AssumptionSha256 = step1AssumptionSha256;
        OnezeroAssumptionSetId = onezeroAssumptionSetId;
        OnezeroAssumptionSha256 = onezeroAssumptionSha256;
        RulePackVersion = rulePackVersion;
        CodeCommit = codeCommit;
        CalculationId = calculationId;
        RunCompletedAt = runCompletedAt;
        SupersededByRunId = supersededByRunId;
        TriggeredBy = triggeredBy;
        Validate();
    }

    /// <summary>The run id.</summary>
    public string RunId { get; init; }

    /// <summary>The client.</summary>
    public long ClientId { get; init; }

    /// <summary>The program code.</summary>
    public string ProgramCode { get; init; }

    /// <summary>The tax year.</summary>
    public long TaxYear { get; init; }

    /// <summary>First day of the fiscal window.</summary>
    public DateOnly FiscalYearBegin { get; init; }

    /// <summary>Last day of the fiscal window.</summary>
    public DateOnly FiscalYearEnd { get; init; }

    /// <summary>When the run started.</summary>
    public PyDateTime RunStartedAt { get; init; }

    /// <summary>The run status.</summary>
    public string RunStatus { get; init; }

    /// <summary>The entity.</summary>
    public long? EntityId { get; init; }

    /// <summary>The payroll snapshot.</summary>
    public string? SourceSnapshotId { get; init; }

    /// <summary>The Step 1 assumption set.</summary>
    public string? Step1AssumptionSetId { get; init; }

    /// <summary>The Step 1 assumption hash.</summary>
    public string? Step1AssumptionSha256 { get; init; }

    /// <summary>The One/Zero assumption set.</summary>
    public string? OnezeroAssumptionSetId { get; init; }

    /// <summary>The One/Zero assumption hash.</summary>
    public string? OnezeroAssumptionSha256 { get; init; }

    /// <summary>The rule pack applied.</summary>
    public string? RulePackVersion { get; init; }

    /// <summary>The commit that executed the run.</summary>
    public string? CodeCommit { get; init; }

    /// <summary>The calculation id.</summary>
    public string? CalculationId { get; init; }

    /// <summary>When the run finished.</summary>
    public PyDateTime? RunCompletedAt { get; init; }

    /// <summary>The run that replaced this one.</summary>
    public string? SupersededByRunId { get; init; }

    /// <summary>Who or what started it.</summary>
    public string? TriggeredBy { get; init; }

    /// <summary>Python <c>dataclasses.replace</c>: applies <paramref name="change"/> (a <c>with</c> expression) and re-validates.</summary>
    /// <param name="change">The edit.</param>
    /// <returns>The validated copy.</returns>
    /// <exception cref="PyValueError">When the edited manifest is invalid.</exception>
    public RunManifest Replace(Func<RunManifest, RunManifest> change)
    {
        ArgumentNullException.ThrowIfNull(change);
        var copy = change(this);
        copy.Validate();
        return copy;
    }

    // The status is judged first, so a bad status on a bad window reports the status, as in Python.
    private void Validate()
    {
        if (!WarehouseVocabulary.RunStatuses.Contains(RunStatus))
        {
            throw new PyValueError(
                $"run_status={PyStr.Repr(RunStatus)} is not one of {WarehouseVocabulary.SortedRepr(WarehouseVocabulary.RunStatuses)}. "
                + "The warehouse will accept any string \u2014 it does not enforce the constraint \u2014 so an unrecognised status "
                + "would sit in the manifest looking authoritative.");
        }

        if (FiscalYearEnd <= FiscalYearBegin)
        {
            throw new PyValueError(
                $"fiscal window {WarehouseVocabulary.Iso(FiscalYearBegin)}..{WarehouseVocabulary.Iso(FiscalYearEnd)} ends on or before it begins.");
        }
    }
}

/// <summary>Where run manifests are recorded (Python <c>RunManifestRepository</c> Protocol; implementations live in infrastructure). <c>Record</c> is append-only: a rerun supersedes its predecessor.</summary>
public interface IRunManifestRepository
{
    /// <summary>Appends one run.</summary>
    /// <param name="manifest">The run.</param>
    /// <returns>What was stored.</returns>
    RunManifest Record(RunManifest manifest);

    /// <summary>One run by id.</summary>
    /// <param name="runId">The run id.</param>
    /// <returns>The run, or <c>null</c> if it was never recorded.</returns>
    RunManifest? Get(string runId);

    /// <summary>The live run for a client (<c>success</c> and not superseded); <c>null</c> means "not yet calculated" and must not render as zero.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">Restrict to one program.</param>
    /// <returns>The run, or <c>null</c>.</returns>
    RunManifest? Latest(long clientId, string? programCode = null);

    /// <summary>How many runs are recorded: the cheapest proof the store is reachable.</summary>
    /// <returns>The count.</returns>
    long Count();
}
