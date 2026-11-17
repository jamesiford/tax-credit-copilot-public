using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Triggers;

namespace TaxCredit.Domain.Qc;

/// <summary>
/// Python <c>tools/qc.py</c>: automated QC with human validation checkpoints (CALC-07 test of twos, CALC-08 meaningful pay periods). Exception-first and
/// never silently dropping a record: every anomaly is surfaced for a reviewer.
/// </summary>
public static class QcDetector
{
    /// <summary>The default <c>min_wages</c>: 50.0 (a float).</summary>
    public static PyNumber DefaultMinWages { get; } = PyNumber.OfFloat(50.0);

    /// <summary>The default <c>min_hours</c>: 4.0 (a float).</summary>
    public static PyNumber DefaultMinHours { get; } = PyNumber.OfFloat(4.0);

    /// <summary>Python <c>_month_key</c>: the <c>YYYY-MM</c> bucket of an ISO pay date (the 1-0 headcount month key).</summary>
    /// <param name="payDate">The pay date cell; only its first 10 characters are read.</param>
    /// <returns>The month key.</returns>
    public static string MonthKey(object? payDate)
    {
        var d = PyDate.FromIsoFormat(PyStr.Prefix(ProximityCoerce.Str(payDate), 10));
        return d.Year.ToString("0000", System.Globalization.CultureInfo.InvariantCulture) + "-" + d.Month.ToString("00", System.Globalization.CultureInfo.InvariantCulture);
    }

    /// <summary>Python <c>_filter</c>: the rows of a tax year (and, when given, a state's <c>XX_</c> worksites).</summary>
    /// <remarks>
    /// Why <c>int()</c>: <c>Tax_Year</c> arrives as text from a CSV and as a number from a warehouse; <c>int("2025")</c> and <c>int(2025.9)</c> both read 2025,
    /// while <c>None</c> and junk text raise.
    /// </remarks>
    /// <param name="rows">The rows.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="state">A state code or <c>null</c>/empty for all.</param>
    /// <returns>The rows kept, in order.</returns>
    public static List<PyDict> Filter(IEnumerable<PyDict> rows, long taxYear, string? state)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var kept = rows.Where(r => ProximityCoerce.ToInt(r.TryGetValue("Tax_Year", out var y) ? y : 0L) is long l && l == taxYear).ToList();
        if (!string.IsNullOrEmpty(state))
        {
            var prefix = PyStr.Upper(state) + "_";
            kept = kept.Where(r => (r.TryGetValue("Worksite_ID", out var w) ? ProximityCoerce.Str(w) : string.Empty).StartsWith(prefix, StringComparison.Ordinal)).ToList();
        }

        return kept;
    }

    /// <summary>Python <c>detect_test_of_twos</c> (CALC-07): one anomaly per (employee, month) counted at more than one unit, with each unit's wages, hours and period count.</summary>
    /// <param name="rows">The payroll rows.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="state">An optional state filter.</param>
    /// <returns>The anomalies sorted by (employee, month); nothing is dropped.</returns>
    public static List<PyDict> DetectTestOfTwos(IEnumerable<PyDict> rows, long taxYear, string? state = null)
    {
        var grouped = new Dictionary<(string Emp, string Month), Dictionary<string, (double Wages, double Hours, long Periods)>>();
        foreach (var r in Filter(rows, taxYear, state))
        {
            var emp = Text(r, "Employee_ID");
            var month = MonthKey(r.TryGetValue("Pay_Date", out var pd) ? pd : "1900-01-01");
            var unit = Text(r, "Worksite_ID");
            if (!grouped.TryGetValue((emp, month), out var units))
            {
                units = new Dictionary<string, (double, double, long)>(StringComparer.Ordinal);
                grouped[(emp, month)] = units;
            }

            var cell = units.GetValueOrDefault(unit);
            units[unit] = (cell.Wages + ProximityCoerce.FloatOrZero(r, "Gross_Wages"), cell.Hours + ProximityCoerce.FloatOrZero(r, "Hours_Worked"), cell.Periods + 1);
        }

        var ordered = grouped.OrderBy(kv => kv.Key, KeyComparer.Instance);
        return ordered.Where(kv => kv.Value.Count > 1).Select(kv => TwosAnomaly(kv.Key.Emp, kv.Key.Month, kv.Value)).ToList();
    }

    /// <summary>Python <c>detect_scraggly_pay_periods</c> (CALC-08): lines with wages below <paramref name="minWages"/> AND hours below <paramref name="minHours"/>, flagged, not removed.</summary>
    /// <param name="rows">The payroll rows.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="state">An optional state filter.</param>
    /// <param name="minWages">Wage threshold (<c>null</c> is 50.0).</param>
    /// <param name="minHours">Hours threshold (<c>null</c> is 4.0).</param>
    /// <returns>One anomaly per flagged line, with its line key.</returns>
    public static List<PyDict> DetectScragglyPayPeriods(IEnumerable<PyDict> rows, long taxYear, string? state = null, PyNumber? minWages = null, PyNumber? minHours = null)
    {
        var scoped = Filter(rows, taxYear, state);
        var keys = PayLineKeys.Keys(scoped);
        var anomalies = new List<PyDict>();
        for (var i = 0; i < scoped.Count; i++)
        {
            var r = scoped[i];
            var wages = ProximityCoerce.FloatOrZero(r, "Gross_Wages");
            var hours = ProximityCoerce.FloatOrZero(r, "Hours_Worked");
            if (PyNumCompare.Below(wages, minWages ?? DefaultMinWages) && PyNumCompare.Below(hours, minHours ?? DefaultMinHours))
            {
                anomalies.Add(new PyDict()
                    .Add("type", "meaningful_pay_period")
                    .Add("line_key", keys[i])
                    .Add("employee_id", Text(r, "Employee_ID"))
                    .Add("worksite_id", Text(r, "Worksite_ID"))
                    .Add("pay_period_start", Raw(r, "Pay_Period_Start"))
                    .Add("pay_period_end", Raw(r, "Pay_Period_End"))
                    .Add("pay_date", Raw(r, "Pay_Date"))
                    .Add("wages", PyRound.Round(wages, 2))
                    .Add("hours", PyRound.Round(hours, 2))
                    .Add("resolution", "human_review")
                    .Add("note", "Trivial-value period — reviewer confirms before dropping structure (hours/wages retained)."));
            }
        }

        return anomalies;
    }

    /// <summary>
    /// Python <c>run_exception_report</c> (AI-02): both anomaly lists plus a summary and the thresholds. <c>clean</c> is true only when both lists are empty;
    /// a calculation-trail step is recorded when a recorder is active.
    /// </summary>
    /// <param name="rows">The payroll rows.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="state">An optional state filter.</param>
    /// <param name="minWages">Wage threshold (<c>null</c> is 50.0); echoed with its type.</param>
    /// <param name="minHours">Hours threshold (<c>null</c> is 4.0); echoed with its type.</param>
    /// <returns>The report tree.</returns>
    public static PyDict RunExceptionReport(IReadOnlyList<PyDict> rows, long taxYear, string? state = null, PyNumber? minWages = null, PyNumber? minHours = null)
    {
        var wageFloor = minWages ?? DefaultMinWages;
        var hourFloor = minHours ?? DefaultMinHours;
        var twos = DetectTestOfTwos(rows, taxYear, state);
        var scraggly = DetectScragglyPayPeriods(rows, taxYear, state, wageFloor, hourFloor);
        long total = twos.Count + scraggly.Count;
        var summary = new PyDict()
            .Add("test_of_twos_count", (long)twos.Count)
            .Add("meaningful_pay_period_count", (long)scraggly.Count)
            .Add("total_anomalies", total)
            .Add("clean", total == 0)
            .Add("requires_human_validation", total > 0);
        var report = new PyDict()
            .Add("tax_year", taxYear)
            .Add("state", string.IsNullOrEmpty(state) ? null : PyStr.Upper(state))
            .Add("test_of_twos", twos.Cast<object?>().ToList())
            .Add("meaningful_pay_period", scraggly.Cast<object?>().ToList())
            .Add("summary", summary)
            .Add("thresholds", new PyDict().Add("min_wages", PyNum.Tree(wageFloor)).Add("min_hours", PyNum.Tree(hourFloor)));
        TrailContext.Current?.Record(
            "Automated QC — test of twos + meaningful pay periods",
            new PyDict().Add("tax_year", taxYear).Add("state", state).Add("rows", (long)Filter(rows, taxYear, state).Count),
            "group(employee,month) unit_count>1 (CALC-07); wages<min AND hours<min (CALC-08)",
            summary,
            "Process § QC — test of twos + scraggly pay periods (human checkpoint)");
        return report;
    }

    private static PyDict TwosAnomaly(string emp, string month, Dictionary<string, (double Wages, double Hours, long Periods)> units) => new PyDict()
        .Add("type", "test_of_twos")
        .Add("employee_id", emp)
        .Add("month", month)
        .Add("unit_count", (long)units.Count)
        .Add("units", units.OrderBy(u => u.Key, PyStr.Comparer).Select(u => (object?)new PyDict()
            .Add("worksite_id", u.Key)
            .Add("wages", PyRound.Round(u.Value.Wages, 2))
            .Add("hours", PyRound.Round(u.Value.Hours, 2))
            .Add("periods", u.Value.Periods)).ToList())
        .Add("resolution", "human_review")
        .Add("note", "Counted at multiple units this month — reviewer confirms which unit owns the headcount (no auto-drop).");

    // Python `str(r.get(key, ""))`.
    private static string Text(PyDict row, string key) => row.TryGetValue(key, out var v) ? ProximityCoerce.Str(v) : string.Empty;

    // Python `r.get(key)`: the cell as stored, `None` when absent.
    private static object? Raw(PyDict row, string key) => row.TryGetValue(key, out var v) ? v : null;

    private sealed class KeyComparer : IComparer<(string Emp, string Month)>
    {
        public static readonly KeyComparer Instance = new();

        public int Compare((string Emp, string Month) x, (string Emp, string Month) y)
        {
            var c = PyStr.Compare(x.Emp, y.Emp);
            return c != 0 ? c : PyStr.Compare(x.Month, y.Month);
        }
    }
}
