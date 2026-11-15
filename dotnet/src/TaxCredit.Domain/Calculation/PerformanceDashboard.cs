using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// The performance dashboard (Python <c>domain/calculation/performance.py</c>): classifies each employee green, yellow or red
/// against the One/Zero floors. A reporting view; it decides nothing statutory and no part of the engine depends on it.
/// </summary>
public static class PerformanceDashboard
{
    private sealed class Slot(string? employeeId, string? worksiteId, RowCell jobTitle, DateOnly first, DateOnly last)
    {
        public string? EmployeeId { get; } = employeeId;

        public string? WorksiteId { get; } = worksiteId;

        public RowCell JobTitle { get; } = jobTitle;

        public double TotalHours { get; set; }

        public double TotalWages { get; set; }

        public DateOnly First { get; set; } = first;

        public DateOnly Last { get; set; } = last;
    }

    private sealed record Classified(string? EmployeeId, string? WorksiteId, string Status, PyDict Row);

    /// <summary>
    /// Python <c>run_performance_dashboard</c>: status mapping is green (at or above <c>1 + margin</c> of both floors),
    /// yellow (within <c>margin</c> of either floor, either direction) and red (more than <c>margin</c> below either).
    /// </summary>
    /// <param name="rows">Payroll rows; the pay-code policy and the pre-flight cleanup are applied first.</param>
    /// <param name="taxYear">Fiscal year label.</param>
    /// <param name="pack">The One/Zero parameters.</param>
    /// <param name="yellowMargin">Headroom either side of a floor (default <c>0.05</c>); echoed with its type.</param>
    /// <param name="perJobUsd">Credit per net-new job (default <c>0.0</c>), rounded for each yellow employee.</param>
    /// <returns>The summary, per-unit colour split and per-employee classification, in Python's key order.</returns>
    public static PyDict Run(IReadOnlyList<PayrollRow> rows, long taxYear, OneZeroPack pack, PyNumber? yellowMargin = null, PyNumber? perJobUsd = null)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(pack);
        var margin = yellowMargin ?? PyNumber.OfFloat(0.05);
        var perJob = perJobUsd ?? PyNumber.OfFloat(0.0);
        var prepared = OneZeroPreprocessing.Preprocess(OneZeroEligibility.ApplyPayCodePolicy(rows, pack), taxYear);
        var employees = Classify(Aggregate(prepared), pack, ProximityCoerce.ToFloat(margin), perJob);
        employees = PySort.Sorted(employees, e => e, Comparer<Classified>.Create(Compare));

        var byStatus = new PyDict().Add("green", 0L).Add("yellow", 0L).Add("red", 0L);
        foreach (var e in employees)
        {
            byStatus.Set(e.Status, (long)byStatus[e.Status]! + 1);
        }

        return new PyDict()
            .Add("tax_year", taxYear)
            .Add("pack_citation", pack.Citation)
            .Add("min_weekly_hours", Echo(pack.MinWeeklyHours))
            .Add("min_weekly_wages", Echo(pack.MinWeeklyWages))
            .Add("yellow_margin", Echo(margin))
            .Add("summary", byStatus)
            .Add("units", UnitSplit(employees))
            .Add("employees", employees.Select(e => (object?)e.Row).ToList())
            .Add("employee_count", (long)employees.Count);
    }

    // Python builds the per-employee slot dict inside setdefault(...), so every row evaluates (and can fail) the whole literal.
    private static List<Slot> Aggregate(IReadOnlyList<PayrollRow> rows)
    {
        var byEmployee = new OrderedDictionary<(bool, string), Slot>();
        foreach (var r in rows)
        {
            var ee = r.RequireEmployeeId();
            var worksite = r.RequireWorksiteId();
            var first = Coerce.ParseIso(r.RequireStart());
            var last = Coerce.ParseIso(r.RequireEnd());
            var key = (ee is null, ee ?? string.Empty);
            if (!byEmployee.TryGetValue(key, out var slot))
            {
                slot = new Slot(ee, worksite, r.JobTitle, first, last);
                byEmployee.Add(key, slot);
            }

            slot.TotalHours += Coerce.ToFloat(r.RequireHours());
            slot.TotalWages += Coerce.ToFloat(r.RequireWages());
            if (first < slot.First)
            {
                slot.First = first;
            }

            if (last > slot.Last)
            {
                slot.Last = last;
            }
        }

        return [.. byEmployee.Values];
    }

    private static List<Classified> Classify(List<Slot> slots, OneZeroPack pack, double margin, PyNumber perJob)
    {
        var minHours = ProximityCoerce.ToFloat(pack.MinWeeklyHours);
        var minWages = ProximityCoerce.ToFloat(pack.MinWeeklyWages);
        var result = new List<Classified>();
        foreach (var slot in slots)
        {
            var days = slot.Last.DayNumber - slot.First.DayNumber;
            var weeks = PyArith.Max((double)days / 7.0, 0.01);
            var avgHours = slot.TotalHours / weeks;
            var avgWages = slot.TotalWages / weeks;
            var hoursRatio = minHours > 0 ? avgHours / minHours : 1.0;
            var wagesRatio = minWages > 0 ? avgWages / minWages : 1.0;
            var worst = PyArith.Min(hoursRatio, wagesRatio);
            var status = worst >= 1.0 + margin ? "green" : worst >= 1.0 - margin ? "yellow" : "red";
            var hoursGap = PyArith.Max(0.0, minHours - avgHours);
            var wagesGap = PyArith.Max(0.0, minWages - avgWages);
            object credit = status == "yellow" ? RoundToInt(perJob) : 0L;
            var row = new PyDict()
                .Add("Employee_ID", slot.EmployeeId)
                .Add("Worksite_ID", slot.WorksiteId)
                .Add("Job_Title", JobTitleValue(slot.JobTitle))
                .Add("weeks_worked", PyRound.Round(weeks, 2))
                .Add("avg_weekly_hours", PyRound.Round(avgHours, 2))
                .Add("avg_weekly_wages", PyRound.Round(avgWages, 2))
                .Add("status", status)
                .Add("hours_gap_per_week", PyRound.Round(hoursGap, 2))
                .Add("wages_gap_per_week", PyRound.Round(wagesGap, 2))
                .Add("annual_hours_to_qualify", PyRound.Round(hoursGap * 52, 1))
                .Add("credit_at_stake_usd", credit);
            result.Add(new Classified(slot.EmployeeId, slot.WorksiteId, status, row));
        }

        return result;
    }

    // `employees.sort(key=(Worksite_ID, status, Employee_ID))`: a None against a str is a TypeError in Python whose message
    // depends on the order the sort happens to compare them in, so that mix is refused instead of guessed at.
    private static int Compare(Classified x, Classified y)
    {
        var c = CompareText(x.WorksiteId, y.WorksiteId);
        if (c != 0)
        {
            return c;
        }

        c = PyStr.Compare(x.Status, y.Status);
        return c != 0 ? c : CompareText(x.EmployeeId, y.EmployeeId);
    }

    private static int CompareText(string? a, string? b)
    {
        if (a is null && b is null)
        {
            return 0;
        }

        return a is null || b is null ? throw new PyUnsupportedException("Ordering None against a str is not modelled") : PyStr.Compare(a, b);
    }

    private static List<object?> UnitSplit(List<Classified> employees)
    {
        var units = new OrderedDictionary<(bool, string), (string? Id, long[] Counts)>();
        foreach (var e in employees)
        {
            var key = (e.WorksiteId is null, e.WorksiteId ?? string.Empty);
            if (!units.TryGetValue(key, out var entry))
            {
                entry = (e.WorksiteId, new long[4]);
                units.Add(key, entry);
            }

            entry.Counts[e.Status == "green" ? 0 : e.Status == "yellow" ? 1 : 2]++;
            entry.Counts[3]++;
        }

        var ordered = PySort.Sorted(units.Values, u => u, Comparer<(string? Id, long[] Counts)>.Create((a, b) => CompareText(a.Id, b.Id)));
        return ordered.Select(u => (object?)new PyDict()
            .Add("Worksite_ID", u.Id).Add("green", u.Counts[0]).Add("yellow", u.Counts[1]).Add("red", u.Counts[2]).Add("total", u.Counts[3])).ToList();
    }

    // `cond ? long : double` would convert the long to a double (conditional-type trap, see slice-domain-log DS2).
#pragma warning disable CA1859 // the object return is the point: the echoed value keeps its Python type
    private static object Echo(PyNumber n)
    {
        if (n.IsInt)
        {
            return n.IntValue;
        }

        return n.FloatValue;
    }
#pragma warning restore CA1859

    private static object? JobTitleValue(RowCell cell) => cell.Kind switch
    {
        CellKind.Absent => string.Empty,
        CellKind.Null => null,
        CellKind.Text => cell.Text,
        CellKind.WholeNumber => cell.IntValue,
        _ => cell.FloatValue,
    };

    // `round(per_job_usd)` with no digits returns an int (NaN is a ValueError, infinity an OverflowError); an int passes through.
#pragma warning disable CA1859 // the object return is the point: a long when it fits, a BigInteger otherwise
    private static object RoundToInt(PyNumber value)
    {
        if (value.IsInt)
        {
            return value.IntValue;
        }

        var rounded = PyRound.RoundToInteger(value.FloatValue);
        if (rounded >= long.MinValue && rounded <= long.MaxValue)
        {
            return (long)rounded;
        }

        return rounded;
    }
#pragma warning restore CA1859
}
