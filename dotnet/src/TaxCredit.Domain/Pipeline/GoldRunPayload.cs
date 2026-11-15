using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

/// <summary>
/// Everything one run hands the Gold writer (the dictionary <c>handle_run_client_calculation</c> passes to <c>write_run</c>): the run's identity, the manifest
/// row and the seven <c>tcc_gold</c> projections, rows in the order the run produced them.
/// </summary>
/// <param name="ClientId">The client.</param>
/// <param name="ProgramCode">The program.</param>
/// <param name="RunId">The run.</param>
/// <param name="RunCompletedAt">The completion stamp the writer records once every row is down.</param>
/// <param name="ManifestColumns">The <c>tcc_ops.run_manifest</c> columns, in DDL order.</param>
/// <param name="ManifestRow">The manifest's values, aligned with <paramref name="ManifestColumns"/> (<c>string</c>, <c>long</c>, <see cref="DateOnly"/>, <see cref="PyDateTime"/> or <c>null</c>).</param>
/// <param name="EmployeePeriodFact">One row per pay period consumed, requested year first.</param>
/// <param name="EmployeeEligibility">Per employee, year and method.</param>
/// <param name="OneZeroMatrix">The qualified employees' monthly matrix.</param>
/// <param name="UnitMonthSummary">Per unit, month grain.</param>
/// <param name="RunMethodSummary">What each method concluded per client-year.</param>
/// <param name="UnitYearMaster">The credit layer per unit-year-method.</param>
/// <param name="UnitCreditInstallment">Creation year by claimable year.</param>
public sealed record GoldRunPayload(
    long ClientId,
    string ProgramCode,
    string RunId,
    PyDateTime RunCompletedAt,
    IReadOnlyList<string> ManifestColumns,
    IReadOnlyList<object?> ManifestRow,
    IReadOnlyList<GoldRow> EmployeePeriodFact,
    IReadOnlyList<GoldRow> EmployeeEligibility,
    IReadOnlyList<GoldRow> OneZeroMatrix,
    IReadOnlyList<GoldRow> UnitMonthSummary,
    IReadOnlyList<GoldRow> RunMethodSummary,
    IReadOnlyList<GoldRow> UnitYearMaster,
    IReadOnlyList<GoldRow> UnitCreditInstallment)
{
    /// <summary>The seven tables in the order the payload dictionary lists them, which is the order of the <c>rows_written</c> counts.</summary>
    public IReadOnlyList<KeyValuePair<string, IReadOnlyList<GoldRow>>> Tables =>
    [
        new("employee_period_fact", EmployeePeriodFact),
        new("employee_eligibility", EmployeeEligibility),
        new("onezero_matrix", OneZeroMatrix),
        new("unit_month_summary", UnitMonthSummary),
        new("run_method_summary", RunMethodSummary),
        new("unit_year_master", UnitYearMaster),
        new("unit_credit_installment", UnitCreditInstallment),
    ];
}

/// <summary>The values the run reads from its surroundings, injected (the clock, the ids, the settings and the assumption files).</summary>
/// <param name="CodeCommit">Python <c>_code_commit()</c>: the commit the engine ran at, at most 40 characters.</param>
/// <param name="Assumptions">Python <c>_assumption_identity()</c>: the active assumption sets with their content hashes.</param>
/// <param name="Section9QueryCount">Python <c>section_9_query_count()</c>.</param>
/// <param name="Today">Python <c>application.open_year.today</c>: the one clock the open-year test reads.</param>
/// <param name="UtcNow">Python <c>datetime.now(timezone.utc)</c> as <c>gold_projection.utc_now</c> reads it.</param>
/// <param name="NewRunId">Python <c>uuid.uuid4().hex</c>.</param>
public sealed record ClientCalculationConfig(
    string CodeCommit,
    IReadOnlyList<AssumptionIdentity> Assumptions,
    long Section9QueryCount,
    Func<DateOnly> Today,
    Func<PyDateTime> UtcNow,
    Func<string> NewRunId);

/// <summary>Python <c>RunClientCalculationCommand</c>: recalculate one client-year and persist it.</summary>
/// <param name="ClientId">The client; must be positive.</param>
/// <param name="TaxYear">The tax year; must be positive.</param>
/// <param name="State">The state, if named.</param>
/// <param name="ProgramCode">The program, if named; it wins over <paramref name="State"/> and fixes it. [F04c.3]</param>
/// <param name="AssessTaxYears">Which years to record a CLAIM for; empty means every year the payroll covers.</param>
/// <param name="Actor">Who is responsible (<c>system</c> by default).</param>
public sealed record RunClientCalculationCommand(
    long ClientId,
    long TaxYear,
    string? State = null,
    string? ProgramCode = null,
    IReadOnlyList<long>? AssessTaxYears = null,
    string Actor = "system")
{
    /// <summary>Python <c>__post_init__</c>: validates the ids, then that a named program and a named state agree.</summary>
    /// <param name="defaults">The program defaults.</param>
    /// <returns>This command.</returns>
    /// <exception cref="PyValueError">When an id is not positive.</exception>
    /// <exception cref="ProgramStateConflict">When the program is not the state's.</exception>
    public RunClientCalculationCommand Validated(ProgramDefaults defaults)
    {
        ArgumentNullException.ThrowIfNull(defaults);
        if (ClientId <= 0)
        {
            throw new PyValueError("client_id is required and must be positive");
        }

        if (TaxYear <= 0)
        {
            throw new PyValueError("tax_year is required and must be positive");
        }

        defaults.CheckProgramState(State, ProgramCode);
        return this;
    }
}
