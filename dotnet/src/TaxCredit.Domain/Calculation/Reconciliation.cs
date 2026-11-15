using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Side-by-side comparison of Pay Period against Min Max (Python <c>ReconciliationReport</c>, a dataclass of lists of dicts).</summary>
/// <param name="Units">Per unit and month differences; each entry is a dict in Python's key order.</param>
/// <param name="EmployeeWeeksDonutHole">Employees whose Pay Period weeks exceed Min Max weeks by more than the tolerance.</param>
/// <param name="EligibilityDisagreements">Employees eligible under one method and not the other.</param>
/// <param name="InvariantViolations">Units where the Pay Period average exceeds the Min Max average (Min Max must never be lower).</param>
/// <param name="InvariantHolds">True when Min Max is at least Pay Period for every unit.</param>
/// <param name="AnnualAveragePp">The Pay Period annual average.</param>
/// <param name="AnnualAverageMm">The Min Max annual average.</param>
/// <param name="AnnualAverageDiff">The difference, rounded to two places.</param>
public sealed record ReconciliationReport(
    IReadOnlyList<PyDict> Units,
    IReadOnlyList<PyDict> EmployeeWeeksDonutHole,
    IReadOnlyList<PyDict> EligibilityDisagreements,
    IReadOnlyList<PyDict> InvariantViolations,
    bool InvariantHolds,
    double AnnualAveragePp,
    double AnnualAverageMm,
    double AnnualAverageDiff);

/// <summary>
/// Running both methods and surfacing where they disagree (Python <c>domain/calculation/reconciliation.py</c>). Comparison, not
/// calculation: it reads two finished results and neither engine calls it.
/// </summary>
public static class Reconciliation
{
    private const double InvariantTolerance = 0.01;
    private const int Months = 12;

    /// <summary>
    /// Python <c>reconcile_methods</c>. The primary invariant is the partner's rule: the Min Max average must never be less than
    /// the Pay Period average; a unit that breaks it is listed, never silently accepted.
    /// </summary>
    /// <param name="pp">The Pay Period result.</param>
    /// <param name="mm">The Min Max result.</param>
    /// <param name="donutHoleToleranceWeeks">How many weeks Pay Period may exceed Min Max before an employee is listed.</param>
    /// <returns>The report.</returns>
    public static ReconciliationReport Reconcile(OneZeroResult pp, OneZeroResult mm, double donutHoleToleranceWeeks = 1.5)
    {
        ArgumentNullException.ThrowIfNull(pp);
        ArgumentNullException.ThrowIfNull(mm);
        var units = UnitDiffs(pp, mm);
        var violations = Violations(units);
        return new ReconciliationReport(
            [.. units.Select(u => u.Row)],
            Donut(pp, mm, donutHoleToleranceWeeks),
            Disagreements(pp, mm),
            violations,
            violations.Count == 0,
            pp.AnnualAverage,
            mm.AnnualAverage,
            PyRound.Round(pp.AnnualAverage - mm.AnnualAverage, 2));
    }

    private sealed record UnitDiff(PyDict Row, string Unit, double PpAverage, double MmAverage, double[] PpTotals, double[] MmTotals);

    // A repeated unit keeps its last row, as `{row["Worksite_ID"]: ... for row in summary}` does.
    private static Dictionary<string, IReadOnlyList<double>> TotalsByUnit(OneZeroResult r)
    {
        var map = new Dictionary<string, IReadOnlyList<double>>(StringComparer.Ordinal);
        foreach (var row in r.Summary)
        {
            map[row.WorksiteId ?? throw new PyUnsupportedException("A None Worksite_ID is not modelled")] = row.MonthTotals;
        }

        return map;
    }

    private static Dictionary<string, double> AveragesByUnit(OneZeroResult r)
    {
        var map = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var kv in r.AverageHeadcount)
        {
            map[kv.Key ?? throw new PyUnsupportedException("A None Worksite_ID is not modelled")] = kv.Value;
        }

        return map;
    }

    private static List<UnitDiff> UnitDiffs(OneZeroResult pp, OneZeroResult mm)
    {
        var ppSummary = TotalsByUnit(pp);
        var mmSummary = TotalsByUnit(mm);
        var ppAvg = AveragesByUnit(pp);
        var mmAvg = AveragesByUnit(mm);
        var names = PySort.Sorted(ppSummary.Keys.Union(mmSummary.Keys, StringComparer.Ordinal), k => k, PyStr.Comparer);
        var result = new List<UnitDiff>();
        foreach (var unit in names)
        {
            // A unit one method never produced reads as twelve int zeros (`[0] * 12`), and its average as the int 0.
            var ppKnown = ppSummary.TryGetValue(unit, out var ppCols);
            var mmKnown = mmSummary.TryGetValue(unit, out var mmCols);
            var diffs = new List<double>();
            for (var i = 0; i < Months; i++)
            {
                diffs.Add(Cell(ppCols, i) - Cell(mmCols, i));
            }

            var ppAverage = ppAvg.TryGetValue(unit, out var pa) ? (object)pa : 0L;
            var mmAverage = mmAvg.TryGetValue(unit, out var ma) ? (object)ma : 0L;
            var row = new PyDict()
                .Add("Worksite_ID", unit)
                .Add("pay_period_totals", Totals(ppKnown, ppCols))
                .Add("min_max_totals", Totals(mmKnown, mmCols))
                .Add("month_diffs", diffs.Select(d => (object?)d).ToList())
                .Add("max_abs_diff", PyArith.Max(diffs.Select(Math.Abs).ToList()))
                .Add("pp_average", ppAverage)
                .Add("mm_average", mmAverage);
            result.Add(new UnitDiff(row, unit, AsDouble(ppAverage), AsDouble(mmAverage), Padded(ppCols), Padded(mmCols)));
        }

        return result;
    }

    private static double AsDouble(object v) => v is double d ? d : (long)v;

    private static double Cell(IReadOnlyList<double>? cols, int i) =>
        cols is null ? 0.0 : i < cols.Count ? cols[i] : throw new PyIndexError("list index out of range");

    private static double[] Padded(IReadOnlyList<double>? cols) => cols is null ? new double[Months] : [.. cols];

    private static List<object?> Totals(bool known, IReadOnlyList<double>? cols) =>
        known ? [.. cols!.Select(c => (object?)c)] : [.. Enumerable.Repeat((object?)0L, Months)];

    private static List<PyDict> Violations(List<UnitDiff> units)
    {
        var result = new List<PyDict>();
        foreach (var u in units)
        {
            if (!(u.PpAverage > u.MmAverage + InvariantTolerance))
            {
                continue;
            }

            var offending = new List<object?>();
            for (var i = 0; i < Months; i++)
            {
                if (u.PpTotals[i] > u.MmTotals[i] + InvariantTolerance)
                {
                    offending.Add((long)(i + 1));
                }
            }

            result.Add(new PyDict()
                .Add("Worksite_ID", u.Unit)
                .Add("pp_average", u.Row["pp_average"])
                .Add("mm_average", u.Row["mm_average"])
                .Add("delta", PyRound.Round(u.PpAverage - u.MmAverage, 2))
                .Add("offending_months", offending));
        }

        return result;
    }

    private static Dictionary<string, double> WeeksByEmployee(OneZeroResult r)
    {
        var map = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var e in r.EligibleEmployees)
        {
            map[e.EmployeeId ?? throw new PyUnsupportedException("A None Employee_ID is not modelled")] = e.WeeksWorked;
        }

        return map;
    }

    // Only employees eligible under BOTH methods: a disagreement is reported separately and would otherwise read as a false positive.
    private static List<PyDict> Donut(OneZeroResult pp, OneZeroResult mm, double tolerance)
    {
        var ppWeeks = WeeksByEmployee(pp);
        var mmWeeks = WeeksByEmployee(mm);
        var both = PySort.Sorted(ppWeeks.Keys.Where(mmWeeks.ContainsKey), k => k, PyStr.Comparer);
        var donut = new List<PyDict>();
        foreach (var ee in both)
        {
            var pw = ppWeeks[ee];
            var mw = mmWeeks[ee];
            if (pw > mw + tolerance)
            {
                donut.Add(new PyDict().Add("Employee_ID", ee).Add("pp_weeks", pw).Add("mm_weeks", mw).Add("delta", PyRound.Round(pw - mw, 2)));
            }
        }

        return donut;
    }

    private static List<PyDict> Disagreements(OneZeroResult pp, OneZeroResult mm)
    {
        var ppEligible = WeeksByEmployee(pp);
        var mmEligible = WeeksByEmployee(mm);
        var different = ppEligible.Keys.Where(k => !mmEligible.ContainsKey(k)).Concat(mmEligible.Keys.Where(k => !ppEligible.ContainsKey(k)));
        return [.. PySort.Sorted(different, k => k, PyStr.Comparer).Select(ee => new PyDict()
            .Add("Employee_ID", ee)
            .Add("pay_period_eligible", ppEligible.ContainsKey(ee))
            .Add("min_max_eligible", mmEligible.ContainsKey(ee)))];
    }
}
