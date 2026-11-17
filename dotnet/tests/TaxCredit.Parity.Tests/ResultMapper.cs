using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Typed engine results to the plain trees the goldens hold (key order and int/float types as Python's <c>to_tree</c>).</summary>
internal static class ResultMapper
{
    private static object? Num(PyNumber n) => TrailValues.Of(n);

    private static object? Cell(RowCell c) => c.Kind switch
    {
        CellKind.Null => null,
        CellKind.Text => c.Text,
        CellKind.WholeNumber => c.IntValue,
        CellKind.Real => c.FloatValue,
        _ => throw new InvalidOperationException("absent"),
    };

    public static List<object?> MapRows(IReadOnlyList<PayrollRow> rows) => rows.Select(r => (object?)MapRow(r)).ToList();

    private static PyDict MapRow(PayrollRow r)
    {
        var d = new PyDict();
        void Put(string key, RowCell c)
        {
            if (c.IsPresent)
            {
                d.Add(key, Cell(c));
            }
        }

        Put("Employee_ID", r.EmployeeId);
        Put("Worksite_ID", r.WorksiteId);
        Put("Entity_FEIN", r.EntityFein);
        Put("Pay_Period_Start", r.PayPeriodStart);
        Put("Pay_Period_End", r.PayPeriodEnd);
        Put("Pay_Date", r.PayDate);
        Put("Hours_Worked", r.HoursWorked);
        Put("Gross_Wages", r.GrossWages);
        Put("Pay_Code", r.PayCode);
        Put("Work_State", r.WorkState);
        return d;
    }

    public static PyDict Map(OneZeroResult r) => new PyDict()
        .Add("method", r.Method)
        .Add("tax_year", r.TaxYear)
        .Add("analysis_start_month", EngineRunner.Iso(r.AnalysisStartMonth))
        .Add("months", r.Months.Select(m => (object?)EngineRunner.Iso(m)).ToList())
        .Add("total_hours_and_wages", r.TotalHoursAndWages.Select(t => (object?)new PyDict().Add("Employee_ID", t.EmployeeId).Add("total_hours", t.TotalHours).Add("total_wages", t.TotalWages)).ToList())
        .Add("eligible_employees", r.EligibleEmployees.Select(a => (object?)Average(a)).ToList())
        .Add("employee_unit_matrix", r.EmployeeUnitMatrix.Select(m => (object?)Matrix(m)).ToList())
        .Add("summary", r.Summary.Select(s => (object?)new PyDict().Add("Worksite_ID", s.WorksiteId).Add("month_totals", s.MonthTotals.Select(c => (object?)c).ToList()).Add("total", s.Total).Add("average_headcount", s.AverageHeadcount)).ToList())
        .Add("average_headcount", AverageHeadcount(r.AverageHeadcount))
        .Add("annual_average", r.AnnualAverage)
        .Add("flags", r.Flags.Select(f => (object?)Flag(f)).ToList())
        .Add("all_averages", r.AllAverages.Select(a => (object?)Average(a)).ToList());

    private static PyDict AverageHeadcount(IReadOnlyList<KeyValuePair<string?, double>> items)
    {
        var d = new PyDict();
        foreach (var kv in items)
        {
            d.Add(kv.Key ?? "null", kv.Value);
        }

        return d;
    }

    private static PyDict Average(AverageRow a)
    {
        var d = new PyDict().Add("Employee_ID", a.EmployeeId).Add("total_hours", a.TotalHours).Add("total_wages", a.TotalWages);
        if (a.Span is { } s)
        {
            d.Add("first_start", s.FirstStart).Add("last_end", s.LastEnd).Add("days", s.Days);
        }

        d.Add("weeks_worked", a.WeeksWorked).Add("avg_weekly_hours", a.AvgWeeklyHours).Add("avg_weekly_wages", a.AvgWeeklyWages);
        if (a.Eligible is not null)
        {
            d.Add("weight", a.Weight).Add("passed_hours", a.PassedHours).Add("passed_wages", a.PassedWages).Add("eligible", a.Eligible);
        }

        return d;
    }

    private static PyDict Matrix(MatrixRow m)
    {
        var d = new PyDict().Add("Employee_ID", m.EmployeeId).Add("Worksite_ID", m.WorksiteId).Add("Entity_FEIN", m.EntityFein);
        if (m.IsMinMax)
        {
            d.Add("first_pps", m.FirstPps).Add("last_ppe", m.LastPpe);
        }
        else
        {
            d.Add("Pay_Period_Start", m.PayPeriodStart).Add("Pay_Period_End", m.PayPeriodEnd).Add("Pay_Date", m.PayDate);
        }

        return d.Add("weight", m.Weight).Add("months", m.Months.Select(Num).ToList());
    }

    private static PyDict Flag(OneZeroFlag f)
    {
        var d = new PyDict().Add("type", f.Type).Add("employee_id", f.EmployeeId);
        if (f.Weeks is { } w)
        {
            return d.Add("weeks", w);
        }

        return d.Add("month_index", f.MonthIndex).Add("count", f.Count is { } c ? Num(c) : null);
    }
}
