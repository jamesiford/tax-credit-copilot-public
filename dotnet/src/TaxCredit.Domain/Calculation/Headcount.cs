using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Average Headcount and the row selection it depends on (Python <c>domain/calculation/headcount.py</c>).</summary>
public static class Headcount
{
    /// <summary><c>row_state</c>: explicit <c>Work_State</c> (stripped, upper-cased) else the two-letter <c>Worksite_ID</c> prefix.</summary>
    /// <param name="row">The row.</param>
    /// <returns>The state, or empty.</returns>
    public static string RowState(PayrollRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        // (row.get("Work_State") or "").strip(): None and "" are both falsy.
        var explicitState = row.WorkState.Kind switch
        {
            CellKind.Text => PyStr.Strip(row.WorkState.Text!),
            CellKind.Absent or CellKind.Null => string.Empty,
            _ => throw new PyUnsupportedException("Numeric Work_State cells are not modelled"),
        };
        if (explicitState.Length > 0)
        {
            return PyStr.Upper(explicitState);
        }

        var worksite = row.WorksiteId.Kind switch
        {
            CellKind.Text => row.WorksiteId.Text!,
            CellKind.Absent or CellKind.Null => string.Empty,
            _ => throw new PyUnsupportedException("Numeric Worksite_ID cells are not modelled"),
        };
        var split = worksite.IndexOf('_', StringComparison.Ordinal);
        if (split < 0)
        {
            return string.Empty;
        }

        var head = worksite[..split];
        return PyStr.Length(head) == 2 ? PyStr.Upper(head) : string.Empty;
    }

    /// <summary><c>states_present</c>: every work state in the rows, sorted and distinct.</summary>
    /// <param name="rows">The rows.</param>
    /// <returns>The states.</returns>
    public static IReadOnlyList<string> StatesPresent(IReadOnlyList<PayrollRow> rows)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var states = new HashSet<string>(StringComparer.Ordinal);
        foreach (var r in rows)
        {
            var s = RowState(r);
            if (s.Length > 0)
            {
                states.Add(s);
            }
        }

        return PySort.Sorted(states, s => s, PyStr.Comparer);
    }

    /// <summary><c>rows_for_state_year</c>: selection by pay date (the certified fiscal trim), never by a Tax_Year column.</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="state">The state.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="window">The client's fiscal window; the calendar year of <paramref name="taxYear"/> when null.</param>
    /// <returns>The selected rows.</returns>
    public static List<PayrollRow> RowsForStateYear(IReadOnlyList<PayrollRow> rows, string state, long taxYear, (DateOnly Begin, DateOnly End)? window = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(state);
        var result = new List<PayrollRow>();
        foreach (var r in rows)
        {
            if (RowState(r) != state)
            {
                continue;
            }

            if (window is null)
            {
                var text = PayDateText(r);
                if (PyStr.Prefix(text, 4) == taxYear.ToString(System.Globalization.CultureInfo.InvariantCulture))
                {
                    result.Add(r);
                }
            }
            else if (window.Value.Begin <= PayDateOrMin(r) && PayDateOrMin(r) <= window.Value.End)
            {
                result.Add(r);
            }
        }

        return result;
    }

    /// <summary>Average Headcount for one state-year, measured over the client's own fiscal window.</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="state">The state.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="pack">Eligibility parameters.</param>
    /// <param name="window">The fiscal window; calendar year when null.</param>
    /// <returns>The annual average, 0.0 when no rows apply.</returns>
    public static double AverageHeadcount(IReadOnlyList<PayrollRow> rows, string state, long taxYear, OneZeroPack pack, (DateOnly Begin, DateOnly End)? window = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(pack);
        var (begin, end) = window ?? (PyDate.Make((int)taxYear, 1, 1), PyDate.Make((int)taxYear, 12, 31));
        var yearRows = RowsForStateYear(rows, state, taxYear, window);
        if (yearRows.Count == 0)
        {
            return 0.0;
        }

        return PayPeriodMethod.Run(
            yearRows,
            taxYear,
            OneZeroCalendar.FirstMeasurableMonth(yearRows, begin, end),
            pack,
            fiscalWindow: (begin, end)).AnnualAverage;
    }

    /// <summary><c>str(row.get("Pay_Date") or "")</c>.</summary>
    private static string PayDateText(PayrollRow r) => r.PayDate.Kind switch
    {
        CellKind.Text => r.PayDate.Text!,
        CellKind.Absent or CellKind.Null => string.Empty,
        _ => throw new PyUnsupportedException("Numeric Pay_Date cells are not modelled"),
    };

    /// <summary><c>_pay_date</c>: unparseable rows sort outside every window (<c>date.min</c>).</summary>
    private static DateOnly PayDateOrMin(PayrollRow r) =>
        PyDate.TryFromIsoFormat(PyStr.Prefix(PayDateText(r), 10), out var d) ? d : DateOnly.MinValue;
}
