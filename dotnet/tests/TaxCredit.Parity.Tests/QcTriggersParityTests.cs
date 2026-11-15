using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Qc;
using TaxCredit.Domain.Triggers;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS7 (ingestion family, QC and triggers): replays every call of <c>parity/goldens/qc_triggers.jsonl.gz</c> (production <c>tools/qc.py</c> and
/// <c>tools/triggers.py</c>, CPython 3.12) against <see cref="QcDetector"/>, <see cref="PayLineKeys"/> and <see cref="TriggerDetector"/>. Trees are compared by type,
/// key order, double bit pattern and exception type plus message; the exception-report trail by its SHA-256 evidence hash.
/// </summary>
public sealed class QcTriggersParityTests
{
    private const string File = "qc_triggers.jsonl.gz";
    private static readonly string[] Functions = ["pay_line_keys", "_line_content", "_month_key", "_filter", "detect_test_of_twos", "detect_scraggly_pay_periods", "run_exception_report", "detect_triggers"];
    private readonly Lazy<List<PyDict>> _payroll = new(() => IngestionGolden.Rows(((PyDict)ClaimGolden.Calls(File).First(c => (string)c["fn"]! == "_payroll")["out"]!)["result"]));

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() => ClaimGolden.AssertAllMatch(File, Invoke, Functions, 1700, 60);

    [Fact]
    public void A_scraggly_key_carries_no_employee_id_and_tells_identical_lines_apart()
    {
        // test_ingestion: the key travels in a URL path, and exact duplicate lines are interchangeable but distinct.
        var line = new PyDict().Add("Employee_ID", "102400664").Add("Worksite_ID", "GA_X").Add("Tax_Year", 2025L).Add("Pay_Date", "2025-03-10").Add("Gross_Wages", -0.24).Add("Hours_Worked", 0.0);
        var keys = PayLineKeys.Keys([line, line]);
        Assert.DoesNotContain("102400664", keys[0], StringComparison.Ordinal);
        Assert.NotEqual(keys[0], keys[1]);
        Assert.Equal(keys[0].Split('.')[0], keys[1].Split('.')[0]);
    }

    [Fact]
    public void A_spike_of_exactly_the_threshold_fires_and_one_fewer_does_not()
    {
        PyDict Row(string emp) => new PyDict().Add("Employee_ID", emp).Add("Worksite_ID", "GA_A").Add("Hours_Worked", 40L).Add("Gross_Wages", 800L).Add("Entity_FEIN", "F");
        List<PyDict> Many(int n) => Enumerable.Range(0, n).Select(i => Row("E" + i)).ToList();
        Assert.Contains(TriggerDetector.Detect(Many(3), Many(8)), t => (string)t["type"]! == "headcount_spike");
        Assert.DoesNotContain(TriggerDetector.Detect(Many(3), Many(7)), t => (string)t["type"]! == "headcount_spike");
    }

    private object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        if (fn == "_payroll")
        {
            return new PyDict().Add("result", _payroll.Value.Cast<object?>().ToList());
        }

        if (a.TryGetValue("trail", out var spec) && spec is PyDict t)
        {
            var recorder = new TrailRecorder((string)t["title"]!, (string)t["citation"]!);
            object? result;
            using (TrailContext.Use(recorder))
            {
                result = Dispatch(fn, a);
            }

            return new PyDict().Add("result", result).Add("trail", recorder.ToDict());
        }

        return new PyDict().Add("result", Dispatch(fn, a));
    }

    private object? Dispatch(string fn, PyDict a) => fn switch
    {
        "pay_line_keys" => Digest(PayLineKeys.Keys(Rows(a["rows"])).Cast<object?>().ToList(), a),
        "_line_content" => PayLineKeys.LineContent((PyDict)a["row"]!),
        "_month_key" => QcDetector.MonthKey(a["pay_date"]),
        "_filter" => QcDetector.Filter(Rows(a["rows"]), (long)a["tax_year"]!, IngestionGolden.Text(a, "state")).Cast<object?>().ToList(),
        "detect_test_of_twos" => QcDetector.DetectTestOfTwos(Rows(a["rows"]), (long)a["tax_year"]!, IngestionGolden.Text(a, "state")).Cast<object?>().ToList(),
        "detect_scraggly_pay_periods" => QcDetector.DetectScragglyPayPeriods(Rows(a["rows"]), (long)a["tax_year"]!, IngestionGolden.Text(a, "state"), IngestionGolden.Number(a, "min_wages"), IngestionGolden.Number(a, "min_hours")).Cast<object?>().ToList(),
        "run_exception_report" => QcDetector.RunExceptionReport(Rows(a["rows"]), (long)a["tax_year"]!, IngestionGolden.Text(a, "state"), IngestionGolden.Number(a, "min_wages"), IngestionGolden.Number(a, "min_hours")),
        "detect_triggers" => TriggerDetector.Detect(Rows(a["prior_rows"]), Rows(a["current_rows"]), IngestionGolden.Number(a, "headcount_spike_min"), IngestionGolden.Number(a, "wage_increase_min_pct")).Cast<object?>().ToList(),
        _ => throw new PyUnsupportedException("unknown function " + fn),
    };

    private static object? Digest(List<object?> items, PyDict a) =>
        a.TryGetValue("digest", out var d) && d is true ? new PyDict().Add("$digest", IngestionGolden.Sha256(items)).Add("n", (long)items.Count) : items;

    // A `rows` argument: literal rows and {"$payroll": selection} parts, flattened in order.
    private List<PyDict> Rows(object? parts)
    {
        var rows = new List<PyDict>();
        foreach (var part in (List<object?>)parts!)
        {
            var d = (PyDict)part!;
            if (d.Count == 1 && d.TryGetValue("$payroll", out var sel))
            {
                rows.AddRange(Select((PyDict)sel!));
            }
            else
            {
                rows.Add(d);
            }
        }

        return rows;
    }

    private List<PyDict> Select(PyDict sel)
    {
        var prefix = IngestionGolden.Text(sel, "prefix");
        var year = IngestionGolden.Text(sel, "year");
        var rows = _payroll.Value.Where(r => (string.IsNullOrEmpty(prefix) || ((string)r["Worksite_ID"]!).StartsWith(prefix, StringComparison.Ordinal))
            && (year is null || (string)r["Tax_Year"]! == year)).ToList();
        if (sel.TryGetValue("max_employees", out var max) && max is long n)
        {
            var keep = rows.Select(r => (string)r["Employee_ID"]!).Distinct().Take((int)n).ToHashSet(StringComparer.Ordinal);
            rows = rows.Where(r => keep.Contains((string)r["Employee_ID"]!)).ToList();
        }

        return rows;
    }
}
