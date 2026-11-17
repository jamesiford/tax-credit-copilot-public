using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>
/// Python <c>tools/gold_projection.py</c>: engine results projected onto the Gold schema. Data in, rows out; no connection, no clock.
/// This part holds the three employee-grain tables (<c>employee_period_fact</c>, <c>employee_eligibility</c>, <c>onezero_matrix</c>).
/// </summary>
/// <remarks>
/// Rows go in as <see cref="PyDict"/> because Python passes loosely typed mappings and the cell type depends on what the cell held
/// (<c>'1972.36'</c> versus <c>1972.36</c> versus <c>Decimal</c>). A key that is absent and a key holding <c>None</c> are different
/// (<c>row["k"]</c> raises, <c>row.get("k")</c> does not), so the dictionary is never flattened into a record here.
/// </remarks>
public static partial class GoldProjection
{
    /// <summary>The Python <c>row.get(key)</c>: <c>null</c> when the key is absent.</summary>
    private static object? Get(PyDict row, string key) => row.TryGetValue(key, out var v) ? v : null;

    /// <summary>Python <c>x or 0</c>: the int 0 stands in for any falsy value.</summary>
    private static object? OrZero(object? value) => GoldValues.Truthy(value) ? value : 0L;

    /// <summary>Python <c>str(x or "")</c>.</summary>
    private static string OrEmpty(object? value) => GoldValues.Truthy(value) ? GoldValues.Str(value) : string.Empty;

    /// <summary>Python <c>str(x or "") or None</c>: a falsy value and the empty text both become <c>None</c>.</summary>
    private static GoldCell OrNone(object? value)
    {
        var text = OrEmpty(value);
        return text.Length == 0 ? GoldCell.Null : GoldCell.OfText(text);
    }

    private static GoldCell Int(BigInteger value) => GoldCell.OfInt(value);

    private static GoldCell Text(string value) => GoldCell.OfText(value);

    /// <summary>A raw int or str the projection passes through untouched (a float or bool would be a different Python type, which this port does not carry).</summary>
    private static GoldCell Raw(object? value) => value switch
    {
        null => GoldCell.Null,
        string s => GoldCell.OfText(s),
        long l => GoldCell.OfInt(l),
        BigInteger b => GoldCell.OfInt(b),
        DateOnly d => GoldCell.OfDate(d),
        _ => throw new PyUnsupportedException("a " + GoldValues.TypeName(value) + " passed through unchanged is not modelled"),
    };

    /// <summary>Python <c>employee_period_fact_rows</c>: one row per pay period, as the run consumed it.</summary>
    /// <remarks>
    /// <c>included</c> is 1 and <c>selection_decision</c> is <c>fiscal_window</c> for everything: these are the rows the resolver already selected.
    /// Rows dropped upstream by the QC filter never reach this function (a gap the Python docstring names). <c>period_days</c> is inclusive of both
    /// ends, and 0 when either date is <c>None</c>.
    /// </remarks>
    /// <param name="payroll">The payroll rows.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="runId">The run.</param>
    /// <returns>The rows.</returns>
    /// <exception cref="PyKeyError">When a row has no <c>Employee_ID</c>.</exception>
    public static IReadOnlyList<GoldRow> EmployeePeriodFactRows(IEnumerable<PyDict> payroll, BigInteger clientId, string programCode, BigInteger taxYear, string runId)
    {
        ArgumentNullException.ThrowIfNull(payroll);
        var columns = GoldColumns.EmployeePeriodFact;
        var output = new List<GoldRow>();
        foreach (var row in payroll)
        {
            var employeeId = GoldValues.Str(row["Employee_ID"]);
            var start = GoldValues.Day(Get(row, "Pay_Period_Start"));
            var end = GoldValues.Day(Get(row, "Pay_Period_End"));
            var token = RecordTokens.RecordToken(clientId, programCode, taxYear, employeeId);
            var worksite = OrNone(Get(row, "Worksite_ID"));
            var fein = OrNone(Get(row, "Entity_FEIN"));
            var title = OrNone(Get(row, "Job_Title"));
            var payDate = GoldValues.Day(Get(row, "Pay_Date"));
            var days = start.Kind == GoldKind.Date && end.Kind == GoldKind.Date ? end.AsDate.DayNumber - start.AsDate.DayNumber + 1 : 0;
            var frequency = OrNone(Get(row, "Pay_Frequency"));
            var hours = GoldValues.Dec(Get(row, "Hours_Worked"));
            var wages = GoldValues.Dec(Get(row, "Gross_Wages"));
            var payCode = OrNone(Get(row, "Pay_Code"));
            output.Add(new GoldRow("employee_period_fact", columns,
            [
                Int(clientId), Int(taxYear), Text(runId), Text(employeeId), Text(token), worksite, fein, title, start, end, payDate,
                Int(days), frequency, hours, wages, payCode, Int(1), Text("fiscal_window"), GoldCell.Null,
            ]));
        }

        return output;
    }

    /// <summary>
    /// Python <c>employee_eligibility_rows</c>: one row per employee per method, for EVERY employee with payroll, not only those the method could
    /// average. The denominator is <paramref name="totals"/>: an employee with hours and wages but no qualifying pay period has no average row and
    /// still gets a row (NULL averages, <c>eligible = 0</c>), because "evaluated and did not qualify" is not "never looked at".
    /// </summary>
    /// <remarks>
    /// Quirks mirrored: a later average row for the same employee replaces an earlier one (a dict comprehension), and an average row that carries
    /// no <c>weight</c> gives a NULL weight, not 1.00 (only a missing row defaults to 1.0). Python tests the row for truthiness, but every average row holds
    /// its <c>Employee_ID</c> (a row without one is a <c>KeyError</c> while the index is built), so that test is only ever "is there a row".
    /// </remarks>
    /// <param name="totals">One row per employee with payroll.</param>
    /// <param name="averages">One row per employee the method averaged.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="method">The method name.</param>
    /// <param name="runId">The run.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<GoldRow> EmployeeEligibilityRows(
        IEnumerable<PyDict> totals, IEnumerable<PyDict> averages, BigInteger clientId, string programCode, BigInteger taxYear, string method, string runId)
    {
        ArgumentNullException.ThrowIfNull(totals);
        ArgumentNullException.ThrowIfNull(averages);
        var byEmployee = new Dictionary<string, PyDict>(StringComparer.Ordinal);
        foreach (var row in averages)
        {
            byEmployee[GoldValues.Str(row["Employee_ID"])] = row;
        }

        var columns = GoldColumns.EmployeeEligibility;
        var output = new List<GoldRow>();
        foreach (var total in totals)
        {
            var employeeId = GoldValues.Str(total["Employee_ID"]);
            var average = byEmployee.GetValueOrDefault(employeeId);
            var token = RecordTokens.RecordToken(clientId, programCode, taxYear, employeeId);
            var hours = GoldValues.Dec(OrZero(Get(total, "total_hours")));
            var wages = GoldValues.Dec(OrZero(Get(total, "total_wages")));
            var first = average is null ? GoldCell.Null : GoldValues.Day(Get(average, "first_start"));
            var last = average is null ? GoldCell.Null : GoldValues.Day(Get(average, "last_end"));
            var days = average is not null && Get(average, "days") is { } d ? Int(GoldValues.ToInt(d)) : GoldCell.Null;
            var weeks = average is null ? GoldCell.Null : GoldValues.Dec(Get(average, "weeks_worked"));
            var avgHours = average is null ? GoldCell.Null : GoldValues.Dec(Get(average, "avg_weekly_hours"));
            var avgWages = average is null ? GoldCell.Null : GoldValues.Dec(Get(average, "avg_weekly_wages"));
            var eligible = average is null ? Int(0) : GoldValues.Flag(Get(average, "eligible"));
            var weight = GoldValues.Dec(average is null ? 1.0 : Get(average, "weight"));
            output.Add(new GoldRow("employee_eligibility", columns,
            [
                Int(clientId), Int(taxYear), Text(method), Text(runId), Text(employeeId), Text(token), hours, wages, first, last, days, weeks,
                avgHours, avgWages, eligible, weight,
            ]));
        }

        return output;
    }

    /// <summary>
    /// Python <c>onezero_matrix_rows</c>: the monthly one/zero allocation, one row per employee per unit segment. Min-Max publishes the span as
    /// <c>first_pps</c>/<c>last_ppe</c>, Pay Period as <c>Pay_Period_Start</c>/<c>Pay_Period_End</c>; the column is NOT NULL, so a row with neither raises.
    /// </summary>
    /// <param name="matrix">The result's PUBLISHED (deduped) matrix.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="method">The method name.</param>
    /// <param name="runId">The run.</param>
    /// <returns>The rows.</returns>
    /// <exception cref="PyValueError">When a row carries no period span under either key shape.</exception>
    public static IReadOnlyList<GoldRow> OneZeroMatrixRows(IEnumerable<PyDict> matrix, BigInteger clientId, string programCode, BigInteger taxYear, string method, string runId)
    {
        ArgumentNullException.ThrowIfNull(matrix);
        var columns = GoldColumns.OneZeroMatrix;
        var output = new List<GoldRow>();
        foreach (var row in matrix)
        {
            var employeeId = GoldValues.Str(row["Employee_ID"]);
            var months = TwelveMonths(Get(row, "months"));
            var firstSource = Get(row, "first_pps");
            var first = GoldValues.Day(GoldValues.Truthy(firstSource) ? firstSource : Get(row, "Pay_Period_Start"));
            var lastSource = Get(row, "last_ppe");
            var last = GoldValues.Day(GoldValues.Truthy(lastSource) ? lastSource : Get(row, "Pay_Period_End"));
            if (first.Kind == GoldKind.Null || last.Kind == GoldKind.Null)
            {
                throw new PyValueError(
                    $"matrix row for employee {PyStr.Repr(employeeId)} carries no period span under either key shape; writing NULL would lose the segment the months were measured over");
            }

            var cells = new List<GoldCell>
            {
                Int(clientId), Int(taxYear), Text(method), Text(runId), Text(employeeId),
                Text(RecordTokens.RecordToken(clientId, programCode, taxYear, employeeId)),
                Text(OrEmpty(Get(row, "Worksite_ID"))), OrNone(Get(row, "Entity_FEIN")), first, last,
                GoldValues.Dec(OrZero(Get(row, "weight"))),
            };
            cells.AddRange(months.Take(12).Select(m => GoldValues.Dec(m)));
            output.Add(new GoldRow("onezero_matrix", columns, cells));
        }

        return output;
    }

    /// <summary>Python <c>list(x or [])</c> then <c>+= [0.0] * (12 - len)</c>: twelve or more month values, padded with float zeros.</summary>
    private static List<object?> TwelveMonths(object? source)
    {
        var months = new List<object?>();
        if (GoldValues.Truthy(source))
        {
            months.AddRange(source as IReadOnlyList<object?> ?? throw new PyUnsupportedException("a month list that is not a list is not modelled"));
        }

        while (months.Count < 12)
        {
            months.Add(0.0);
        }

        return months;
    }
}
