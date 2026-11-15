using System.Globalization;
using System.Numerics;
using System.Text;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>
/// What <c>run_method_summary_row</c> reads of an engine result (<c>annual_average</c>, the lengths of three lists, the flags and the month ends).
/// The engine result itself is a Python dataclass; only these members matter to the projection.
/// </summary>
/// <param name="AnnualAverage">The annual average as the engine produced it (a float; <c>_dec</c> takes any number).</param>
/// <param name="EligibleEmployees">The length of <c>eligible_employees</c>.</param>
/// <param name="TotalHoursAndWages">The length of <c>total_hours_and_wages</c> (employees evaluated).</param>
/// <param name="EmployeeUnitMatrix">The length of <c>employee_unit_matrix</c>.</param>
/// <param name="Flags">The data-quality flags (<c>result.flags</c>); <c>null</c> reads as empty (Python <c>flags or []</c>).</param>
/// <param name="Months">The twelve measuring dates (<see cref="DateOnly"/> or <see cref="PyDateTime"/>).</param>
public sealed record RunMethodResult(
    object? AnnualAverage,
    long EligibleEmployees,
    long TotalHoursAndWages,
    long EmployeeUnitMatrix,
    IReadOnlyList<PyDict>? Flags,
    IReadOnlyList<object?> Months);

/// <summary>The summary-grain tables of <c>tools/gold_projection.py</c>: <c>run_method_summary</c>, <c>unit_month_summary</c> and the clock seam.</summary>
public static partial class GoldProjection
{
    private const string ContestedFlag = "multi_unit_double_count";

    /// <summary>
    /// Python <c>run_method_summary_row</c>: what one method concluded about one client-year, as a whole. <c>contested_months</c> cannot be recovered
    /// from any other table (the matrix is deduped before it is written, so a contest leaves no trace in the rows it produced).
    /// </summary>
    /// <remarks><c>month_ends</c> is <c>json.dumps([...isoformat()])</c> with Python's DEFAULT separators (<c>", "</c>), not the compact form used elsewhere.</remarks>
    /// <param name="result">The engine result's facts.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="programCode">The programme.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="method">The method name.</param>
    /// <param name="runId">The run.</param>
    /// <param name="unitFeinRows">The number of unit x FEIN summary rows.</param>
    /// <param name="appendedAt">The run's one clock reading.</param>
    /// <returns>The row.</returns>
    public static GoldRow RunMethodSummaryRow(
        RunMethodResult result, BigInteger clientId, string programCode, BigInteger taxYear, string method, string runId, BigInteger unitFeinRows, PyDateTime appendedAt)
    {
        ArgumentNullException.ThrowIfNull(result);
        var contested = (result.Flags ?? []).Count(f => Get(f, "type") is string t && string.Equals(t, ContestedFlag, StringComparison.Ordinal));
        var annual = GoldValues.Dec(result.AnnualAverage);
        var cells = new List<GoldCell>
        {
            Int(clientId), Int(taxYear), Text(method), Text(runId), Text(programCode), annual, Int(result.EligibleEmployees),
            Int(result.TotalHoursAndWages), Int(result.EmployeeUnitMatrix), Int(unitFeinRows), Int(contested), Text(MonthEnds(result.Months)),
            GoldCell.OfDateTime(appendedAt),
        };
        return new GoldRow("run_method_summary", GoldColumns.RunMethodSummary, cells);
    }

    /// <summary>
    /// Python <c>unit_month_summary_rows</c>: per unit, per month. <c>average_headcount</c> is whatever the summary carries (the engine divides by 12 ALWAYS,
    /// including months that scored zero and months no pay period could reach, as the partner's Access output does); <c>unreachable_months</c> is
    /// the COMMA-separated list of the engine's zero-based month indexes, or <c>None</c> when there are none.
    /// </summary>
    /// <param name="summary">The per-unit summary rows.</param>
    /// <param name="clientId">The client.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="method">The method name.</param>
    /// <param name="runId">The run.</param>
    /// <param name="unreachable">The month positions no pay period reaches.</param>
    /// <returns>The rows.</returns>
    public static IReadOnlyList<GoldRow> UnitMonthSummaryRows(IEnumerable<PyDict> summary, BigInteger clientId, BigInteger taxYear, string method, string runId, IReadOnlyList<long> unreachable)
    {
        ArgumentNullException.ThrowIfNull(summary);
        ArgumentNullException.ThrowIfNull(unreachable);
        var csv = string.Join(",", unreachable.Select(i => i.ToString(CultureInfo.InvariantCulture)));
        var columns = GoldColumns.UnitMonthSummary;
        var output = new List<GoldRow>();
        foreach (var row in summary)
        {
            var totals = TwelveMonths(Get(row, "month_totals"));
            var cells = new List<GoldCell> { Int(clientId), Int(taxYear), Text(method), Text(runId), Text(GoldValues.Str(row["Worksite_ID"])) };
            cells.AddRange(totals.Take(12).Select(t => GoldValues.Dec(t)));
            cells.Add(GoldValues.Dec(OrZero(Get(row, "total"))));
            cells.Add(GoldValues.Dec(OrZero(Get(row, "average_headcount"))));
            cells.Add(Int(totals.Take(12).Count(GoldValues.Truthy)));
            cells.Add(csv.Length == 0 ? GoldCell.Null : Text(csv));
            output.Add(new GoldRow("unit_month_summary", columns, cells));
        }

        return output;
    }

    /// <summary>
    /// Python <c>utc_now()</c>: one clock reading per run, so every row of it shares an <c>appended_at</c>, with the zone dropped and microseconds truncated.
    /// The clock is injected: this module never reads it (Python reads <c>datetime.now(timezone.utc)</c> inline).
    /// </summary>
    /// <param name="clock">A UTC clock (an aware <see cref="PyDateTime"/>).</param>
    /// <returns>A naive datetime with microsecond 0.</returns>
    public static PyDateTime UtcNow(Func<PyDateTime> clock)
    {
        ArgumentNullException.ThrowIfNull(clock);
        return clock() with { OffsetMinutes = null, Microsecond = 0 };
    }

    private static string MonthEnds(IReadOnlyList<object?> months)
    {
        var text = new StringBuilder("[");
        for (var i = 0; i < months.Count; i++)
        {
            text.Append(i == 0 ? string.Empty : ", ").Append('"').Append(IsoFormat(months[i])).Append('"');
        }

        return text.Append(']').ToString();
    }

    /// <summary>Python <c>x.isoformat()</c> for a date or datetime; any other value has no such attribute.</summary>
    internal static string IsoFormat(object? value) => value switch
    {
        DateOnly d => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
        PyDateTime t => t.IsoFormat(),
        _ => throw new PyAttributeError($"'{GoldValues.TypeName(value)}' object has no attribute 'isoformat'"),
    };
}
