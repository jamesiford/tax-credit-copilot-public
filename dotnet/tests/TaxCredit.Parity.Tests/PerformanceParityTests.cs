using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS5 (performance, reconciliation, rollups): replays every call of <c>parity/goldens/performance.jsonl.gz</c> (production
/// <c>domain/calculation/{performance,reconciliation,rollups}.py</c> on CPython 3.12) against <see cref="PerformanceDashboard"/>,
/// <see cref="Reconciliation"/> and <see cref="Rollups"/>. Trees are compared by type, key order, double bit pattern and exception type plus message.
/// </summary>
public sealed class PerformanceParityTests
{
    private const string File = "performance.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(
            File,
            Invoke,
            ["run_performance_dashboard", "reconcile_methods", "rollup_matrix_by_field", "rollup_matrix_by_two_fields"],
            minimumCalls: 3000,
            minimumErrors: 60);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(File, Invoke, ["ulp", "int-as-float", "float-as-int", "tie-order", "key-order", "bool-flip"], take: 4000);

    [Fact]
    public void A_yellow_employee_carries_the_rounded_per_job_credit_and_a_green_one_none()
    {
        var pack = new OneZeroPack { MinWeeklyHours = PyNumber.OfFloat(35.0), MinWeeklyWages = PyNumber.OfFloat(686.0), Citation = "t" };
        PayrollRow Row(string id, double hours) => new(
            RowCell.OfText(id), RowCell.OfText("GA_A"), RowCell.OfText("x"), RowCell.OfText("2024-01-01"), RowCell.OfText("2024-01-08"),
            RowCell.OfText("2024-01-13"), RowCell.OfFloat(hours), RowCell.OfFloat(900.0), RowCell.OfText("Regular"), RowCell.Absent);
        var result = PerformanceDashboard.Run([Row("Y", 36.0), Row("G", 45.0)], 2024, pack, perJobUsd: PyNumber.OfFloat(3500.5));
        var employees = (List<object?>)result["employees"]!;
        Assert.Equal(["G", "Y"], employees.Select(e => ((PyDict)e!)["Employee_ID"]));
        Assert.Equal(0L, ((PyDict)employees[0]!)["credit_at_stake_usd"]);
        Assert.Equal(3500L, ((PyDict)employees[1]!)["credit_at_stake_usd"]);
    }

    private static object? Invoke(PyDict call)
    {
        var a = (PyDict)call["args"]!;
        switch ((string)call["fn"]!)
        {
            case "run_performance_dashboard":
                return PerformanceDashboard.Run(
                    ((List<object?>)a["rows"]!).Select(r => Row((PyDict)r!)).ToList(),
                    (long)a["tax_year"]!,
                    Pack((PyDict)a["pack"]!),
                    a.TryGetValue("yellow_margin", out var ym) ? Number(ym) : null,
                    a.TryGetValue("per_job_usd", out var pj) ? Number(pj) : null);
            case "reconcile_methods":
                var tolerance = a.TryGetValue("donut_hole_tolerance_weeks", out var t) ? ToDouble(t) : 1.5;
                return Tree(Reconciliation.Reconcile(Result((PyDict)a["pp"]!, "pay_period"), Result((PyDict)a["mm"]!, "min_max"), tolerance));
            case "rollup_matrix_by_field":
                return Rollups.ByField(Matrix(a["matrix"]), (string)a["field"]!);
            case "rollup_matrix_by_two_fields":
                return Rollups.ByTwoFields(Matrix(a["matrix"]), (string)a["field_a"]!, (string)a["field_b"]!).Cast<object?>().ToList();
            default:
                throw new PyUnsupportedException("unknown function " + call["fn"]);
        }
    }

    private static List<PyDict> Matrix(object? tree) => ((List<object?>)tree!).Cast<PyDict>().ToList();

    private static RowCell Cell(PyDict row, string key) =>
        !row.TryGetValue(key, out var v)
            ? RowCell.Absent
            : v switch
            {
                null => RowCell.Null,
                string s => RowCell.OfText(s),
                long l => RowCell.OfInt(l),
                double d => RowCell.OfFloat(d),
                _ => throw new PyUnsupportedException("cell of type " + v.GetType().Name),
            };

    private static PayrollRow Row(PyDict o) => new(
        Cell(o, "Employee_ID"), Cell(o, "Worksite_ID"), Cell(o, "Entity_FEIN"), Cell(o, "Pay_Period_Start"), Cell(o, "Pay_Period_End"),
        Cell(o, "Pay_Date"), Cell(o, "Hours_Worked"), Cell(o, "Gross_Wages"), Cell(o, "Pay_Code"), Cell(o, "Work_State"), Cell(o, "Job_Title"));

    private static PyNumber Number(object? v) => v is long l ? PyNumber.OfInt(l) : PyNumber.OfFloat((double)v!);

    private static double ToDouble(object? v) => v is long l ? l : (double)v!;

    private static string[]? Codes(PyDict p, string key) =>
        p.TryGetValue(key, out var v) && v is List<object?> list ? list.Select(x => (string)x!).ToArray() : null;

    private static OneZeroPack Pack(PyDict p) => new()
    {
        MinWeeklyHours = Number(p["min_weekly_hours"]),
        MinWeeklyWages = Number(p["min_weekly_wages"]),
        Citation = p.TryGetValue("citation", out var c) ? (string)c! : string.Empty,
        IncludedPayCodes = Codes(p, "included_pay_codes"),
        ExcludedPayCodes = Codes(p, "excluded_pay_codes"),
    };

    // Only the five fields reconcile_methods reads are carried; the exporter records exactly those.
    private static OneZeroResult Result(PyDict r, string method)
    {
        var summary = ((List<object?>)r["summary"]!).Cast<PyDict>()
            .Select(s => new UnitSummary((string?)s["Worksite_ID"], ((List<object?>)s["month_totals"]!).Select(x => ToDouble(x)).ToList(), 0, 0)).ToList();
        var averages = ((PyDict)r["average_headcount"]!).Select(kv => new KeyValuePair<string?, double>(kv.Key, ToDouble(kv.Value))).ToList();
        var eligible = ((List<object?>)r["eligible_employees"]!).Cast<PyDict>()
            .Select(e => new AverageRow { EmployeeId = (string?)e["Employee_ID"], WeeksWorked = ToDouble(e["weeks_worked"]) }).ToList();
        return new OneZeroResult(method, 2025, new DateOnly(2025, 1, 1), [], [], eligible, [], summary, averages, ToDouble(r["annual_average"]), [], []);
    }

    private static PyDict Tree(ReconciliationReport r) => new PyDict()
        .Add("units", r.Units.Cast<object?>().ToList())
        .Add("employee_weeks_donut_hole", r.EmployeeWeeksDonutHole.Cast<object?>().ToList())
        .Add("eligibility_disagreements", r.EligibilityDisagreements.Cast<object?>().ToList())
        .Add("invariant_violations", r.InvariantViolations.Cast<object?>().ToList())
        .Add("invariant_holds", r.InvariantHolds)
        .Add("annual_average_pp", r.AnnualAveragePp)
        .Add("annual_average_mm", r.AnnualAverageMm)
        .Add("annual_average_diff", r.AnnualAverageDiff);
}
