using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Calculations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Calculations;

public sealed class EmployeeRestOfYearTests
{
    [Fact]
    public void Split_pay_codes_share_one_period_target_and_closed_pay_is_untouched()
    {
        var rows = new[]
        {
            Line("2025-01-01", "2025-01-14", 70, 1400),
            Line("2025-01-15", "2025-01-28", 30, 600),
            Line("2025-01-15", "2025-01-28", 10, 200),
        };
        var (moved, applied) = EmployeeRestOfYear.Apply(rows, "test-employee", new DateOnly(2025, 1, 14), 4, hourlyRaise: 1.5);
        Assert.Same(rows[0], moved[0]);
        var pace = 70 / (13 / 7.0);
        Assert.Equal((pace + 4) * 2, moved.Skip(1).Sum(row => Convert.ToDouble(row.Get("Hours_Worked"), System.Globalization.CultureInfo.InvariantCulture)), 10);
        Assert.Equal((pace + 4) * 2 * 21.5, moved.Skip(1).Sum(row => Convert.ToDouble(row.Get("Gross_Wages"), System.Globalization.CultureInfo.InvariantCulture)), 10);
        Assert.Equal(1L, applied["periods_changed"]);
        Assert.Equal(30.0, rows[1].Get("Hours_Worked"));
    }

    [Fact]
    public void Open_year_projects_only_periods_paid_inside_the_window()
    {
        var row = Line("2025-01-01", "2025-01-14", 70, 1400);
        var (moved, applied) = EmployeeRestOfYear.Apply([row], "test-employee", new DateOnly(2025, 1, 14), 0, new DateOnly(2025, 2, 1));
        Assert.Equal(2, moved.Count);
        Assert.Equal("2025-01-28", moved[1].Get("Pay_Date"));
        Assert.Equal(1L, applied["periods_projected"]);
        Assert.Same(row, moved[0]);
    }

    [Fact]
    public void Missing_checkpoint_pace_and_closed_employee_year_are_explicit_refusals()
    {
        var row = Line("2025-01-01", "2025-01-14", 70, 1400);
        Assert.Equal(404, Assert.Throws<ReadRefusalException>(() => EmployeeRestOfYear.Apply([row], "test-employee", new DateOnly(2024, 12, 31), 4)).StatusCode);
        Assert.Equal(404, Assert.Throws<ReadRefusalException>(() => EmployeeRestOfYear.Apply([row], "test-employee", new DateOnly(2025, 2, 1), 4)).StatusCode);
    }

    private static PayRow Line(string start, string end, double hours, double wages) => PayRow.Of(new PyDict()
        .Add("Employee_ID", "test-employee").Add("Worksite_ID", "GA_TEST").Add("Entity_FEIN", "synthetic-entity")
        .Add("Pay_Period_Start", start).Add("Pay_Period_End", end).Add("Pay_Date", end)
        .Add("Hours_Worked", hours).Add("Gross_Wages", wages).Add("Pay_Code", "Regular").Add("Tax_Year", 2025L));
}
