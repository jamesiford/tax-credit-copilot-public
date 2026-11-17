using System.Globalization;

namespace TaxCredit.Domain.Gold;

/// <summary>
/// One Gold row: the table it is for, its columns in DDL order and one typed cell per column. Python emits a bare tuple whose
/// positions agree with the <c>*_COLUMNS</c> constant; carrying the columns with the cells lets a test check that agreement.
/// </summary>
public sealed class GoldRow
{
    /// <summary>Creates a row.</summary>
    /// <param name="table">The <c>tcc_gold</c> table name.</param>
    /// <param name="columns">The columns, in DDL order.</param>
    /// <param name="cells">One cell per column.</param>
    /// <exception cref="ArgumentException">When the counts differ.</exception>
    public GoldRow(string table, IReadOnlyList<string> columns, IReadOnlyList<GoldCell> cells)
    {
        ArgumentNullException.ThrowIfNull(columns);
        ArgumentNullException.ThrowIfNull(cells);
        if (columns.Count != cells.Count)
        {
            throw new ArgumentException($"{table}: {cells.Count} cells for {columns.Count} columns");
        }

        Table = table;
        Columns = columns;
        Cells = cells;
    }

    /// <summary>The table name (without schema).</summary>
    public string Table { get; }

    /// <summary>The column names, in DDL order.</summary>
    public IReadOnlyList<string> Columns { get; }

    /// <summary>The cells, aligned with <see cref="Columns"/>.</summary>
    public IReadOnlyList<GoldCell> Cells { get; }

    /// <summary>The cell of a named column (Python <c>dict(zip(COLUMNS, row))[name]</c>).</summary>
    /// <param name="column">The column.</param>
    public GoldCell this[string column]
    {
        get
        {
            for (var i = 0; i < Columns.Count; i++)
            {
                if (string.Equals(Columns[i], column, StringComparison.Ordinal))
                {
                    return Cells[i];
                }
            }

            throw new KeyNotFoundException(column);
        }
    }
}

/// <summary>The column lists of the seven <c>tcc_gold</c> projections (the <c>*_COLUMNS</c> tuples of <c>tools/gold_projection.py</c>).</summary>
public static class GoldColumns
{
    private static string[] Months() => [.. Enumerable.Range(1, 12).Select(i => "month_" + i.ToString("D2", CultureInfo.InvariantCulture))];

    /// <summary><c>EMPLOYEE_PERIOD_FACT_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> EmployeePeriodFact { get; } =
    [
        "client_id", "tax_year", "run_id", "employee_id", "record_token", "worksite_id", "entity_fein", "job_title", "pay_period_start",
        "pay_period_end", "pay_date", "period_days", "pay_frequency_code", "hours", "wages", "pay_code", "included", "selection_decision", "qc_flag",
    ];

    /// <summary><c>EMPLOYEE_ELIGIBILITY_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> EmployeeEligibility { get; } =
    [
        "client_id", "tax_year", "method", "run_id", "employee_id", "record_token", "total_hours", "total_wages", "first_start", "last_end",
        "days", "weeks_worked", "avg_weekly_hours", "avg_weekly_wages", "eligible", "weight",
    ];

    /// <summary><c>ONEZERO_MATRIX_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> OneZeroMatrix { get; } =
    [
        "client_id", "tax_year", "method", "run_id", "employee_id", "record_token", "worksite_id", "entity_fein", "first_pps", "last_ppe", "weight",
        .. Months(),
    ];

    /// <summary><c>RUN_METHOD_SUMMARY_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> RunMethodSummary { get; } =
    [
        "client_id", "tax_year", "method", "run_id", "program_code", "annual_average", "eligible_employees", "employees_evaluated",
        "matrix_rows", "unit_fein_rows", "contested_months", "month_ends", "appended_at",
    ];

    /// <summary><c>UNIT_MONTH_SUMMARY_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> UnitMonthSummary { get; } =
    [
        "client_id", "tax_year", "method", "run_id", "worksite_id", .. Months(), "total", "average_headcount", "months_with_headcount", "unreachable_months",
    ];

    /// <summary><c>UNIT_YEAR_MASTER_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> UnitYearMaster { get; } =
    [
        "client_id", "worksite_id", "entity_fein", "program_code", "method", "tax_year", "average_headcount", "is_base_year",
        "base_average_headcount", "base_year_source", "net_new_vs_base", "months_reachable", "year_complete", "declined", "decline_reason",
        "threshold", "threshold_source", "qualified", "status", "tier", "designation", "tier_source", "eligible_jobs", "new_jobs_created",
        "high_water_mark", "backfilled", "per_job_usd", "tranche_years", "annual_credit_usd", "base_year_overridden",
        "high_water_mark_overridden", "run_id", "is_current", "appended_at",
    ];

    /// <summary><c>UNIT_CREDIT_INSTALLMENT_COLUMNS</c>.</summary>
    public static IReadOnlyList<string> UnitCreditInstallment { get; } =
    [
        "client_id", "worksite_id", "program_code", "method", "creation_year", "tax_year", "tranche_jobs", "jobs_maintained", "per_job_usd",
        "claimable_usd", "projected", "run_id", "is_current", "appended_at",
    ];

    /// <summary>Every table with its columns, in the order the Python module declares them.</summary>
    public static IReadOnlyDictionary<string, IReadOnlyList<string>> All { get; } = new Dictionary<string, IReadOnlyList<string>>
    {
        ["employee_period_fact"] = EmployeePeriodFact,
        ["employee_eligibility"] = EmployeeEligibility,
        ["onezero_matrix"] = OneZeroMatrix,
        ["run_method_summary"] = RunMethodSummary,
        ["unit_month_summary"] = UnitMonthSummary,
        ["unit_year_master"] = UnitYearMaster,
        ["unit_credit_installment"] = UnitCreditInstallment,
    };
}
