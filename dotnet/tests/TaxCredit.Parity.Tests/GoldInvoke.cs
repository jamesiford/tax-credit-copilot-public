using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Replays one call of <c>gold.jsonl.gz</c> against the C# port.</summary>
internal static class GoldInvoke
{
    private static readonly Lazy<Dictionary<string, (List<PayrollRow> Engine, List<PyDict> Payroll)>> Datasets = new(LoadDatasets);

    public static object? Invoke(PyDict call)
    {
        var a = (PyDict)GoldReplay.Decode(call["args"])!;
        switch ((string)call["fn"]!)
        {
            case "columns":
                return GoldColumns.All.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value.Select(c => (object?)c).ToList()));
            case "_dec":
                return GoldReplay.Cell(GoldValues.Dec(a["value"], (int)(long)a["places"]!));
            case "_day":
                return GoldReplay.Cell(GoldValues.Day(a["value"]));
            case "_flag":
                return GoldReplay.Cell(GoldValues.Flag(a["value"]));
            case "record_token":
                return RecordTokens.RecordToken(GoldReplay.MaybeInt(a["account_id"]), (string)a["program_code"]!, GoldReplay.Int(a["tax_year"]), (string)a["employee_id"]!);
            case "utc_now":
                return GoldReplay.Cell(GoldCell.OfDateTime(GoldProjection.UtcNow(() => (PyDateTime)a["now"]!)));
            case "calculation_id":
                return GoldProjection.CalculationId(
                    a["client_id"], (string)a["program_code"]!, a["tax_year"], a["window_begin"], a["window_end"], (PyDict)a["floors"]!,
                    (List<object?>)a["assumption_ids"]!, GoldReplay.Rows(a["rows"]));
            case "pipeline":
                return Pipeline(call);
            default:
                return Table(call, a);
        }
    }

    /// <summary>The rows a table-producing call builds, for tests that look at the cells themselves.</summary>
    public static (string Table, IReadOnlyList<GoldRow> Rows) RowsOf(PyDict call) => Build(call, (PyDict)GoldReplay.Decode(call["args"])!);

    private static PyDict Table(PyDict call, PyDict a)
    {
        var (name, rows) = Build(call, a);
        return Tree(name, rows);
    }

    private static (string Table, IReadOnlyList<GoldRow> Rows) Build(PyDict call, PyDict a)
    {
        var client = GoldReplay.Int(a["client_id"]);
        switch ((string)call["fn"]!)
        {
            case "employee_period_fact_rows":
                return ("employee_period_fact", GoldProjection.EmployeePeriodFactRows(GoldReplay.Rows(a["payroll"]), client, Str(a, "program_code"), GoldReplay.Int(a["tax_year"]), Str(a, "run_id")));
            case "employee_eligibility_rows":
                return ("employee_eligibility", GoldProjection.EmployeeEligibilityRows(
                    GoldReplay.Rows(a["totals"]), GoldReplay.Rows(a["averages"]), client, Str(a, "program_code"), GoldReplay.Int(a["tax_year"]), Str(a, "method"), Str(a, "run_id")));
            case "onezero_matrix_rows":
                return ("onezero_matrix", GoldProjection.OneZeroMatrixRows(
                    GoldReplay.Rows(a["matrix"]), client, Str(a, "program_code"), GoldReplay.Int(a["tax_year"]), Str(a, "method"), Str(a, "run_id")));
            case "unit_month_summary_rows":
                return ("unit_month_summary", GoldProjection.UnitMonthSummaryRows(
                    GoldReplay.Rows(a["summary"]), client, GoldReplay.Int(a["tax_year"]), Str(a, "method"), Str(a, "run_id"), Longs(a["unreachable"])));
            case "run_method_summary_row":
                return ("run_method_summary", [GoldProjection.RunMethodSummaryRow(
                    RunResult((PyDict)a["result"]!), client, Str(a, "program_code"), GoldReplay.Int(a["tax_year"]), Str(a, "method"), Str(a, "run_id"),
                    GoldReplay.Int(a["unit_fein_rows"]), (PyDateTime)a["appended_at"]!)]);
            case "unit_year_master_row":
                return ("unit_year_master", [GoldProjection.UnitYearMasterRow(Key(a), Stair(a["stair"]), Trend(a["trend"]), (PyDict)a["unit_year"]!, (PyDateTime)a["appended_at"]!)]);
            case "unit_credit_installment_rows":
                return ("unit_credit_installment", GoldProjection.UnitCreditInstallmentRows(
                    Trend(a["trend"]), client, Str(a, "worksite_id"), Str(a, "program_code"), Str(a, "method"), Longs(a["years_with_data"]), Str(a, "run_id"), (PyDateTime)a["appended_at"]!));
            default:
                throw new PyUnsupportedException("unknown function " + call["fn"]);
        }
    }

    public static PyDict Tree(string table, IReadOnlyList<GoldRow> rows)
    {
        GoldReplay.AssertColumns(rows);
        return GoldReplay.Table(table, rows);
    }

    private static string Str(PyDict a, string key) => (string)a[key]!;

    private static object? Get(PyDict d, string key) => d.TryGetValue(key, out var v) ? v : null;

    private static List<long> Longs(object? v) => ((List<object?>)v!).Select(x => (long)x!).ToList();

    private static RunMethodResult RunResult(PyDict r) => new(
        r["annual_average"], (long)r["n_eligible"]!, (long)r["n_totals"]!, (long)r["n_matrix"]!,
        r["flags"] is List<object?> flags ? flags.Cast<PyDict>().ToList() : null, (List<object?>)r["months"]!);

    private static UnitYearKey Key(PyDict a) => new(
        GoldReplay.Int(a["client_id"]), Str(a, "worksite_id"), (string?)a["entity_fein"], Str(a, "program_code"), Str(a, "method"), GoldReplay.Int(a["tax_year"]),
        GoldReplay.Int(a["base_year"]), Str(a, "base_year_source"), GoldReplay.Int(a["months_reachable"]), (bool)a["declined"]!, (string?)a["decline_reason"],
        Str(a, "threshold_source"), Str(a, "status"), (string?)a["tier"], (string?)a["designation"], Str(a, "tier_source"), Str(a, "run_id"));

    private static StairView? Stair(object? t) => t is PyDict d
        ? new StairView(Get(d, "net_new"), Get(d, "threshold"), Get(d, "qualified"), Get(d, "eligible_jobs"), Get(d, "new_jobs_created"), Get(d, "high_water_mark"),
            Get(d, "backfilled"), Get(d, "annual_credit_usd"), Get(d, "per_job_usd"))
        : null;

    private static BaseYearView Trend(object? t)
    {
        var d = (PyDict)t!;
        var events = ((List<object?>)d["tranche_events"]!).Cast<PyDict>()
            .Select(e => new TrancheEventView(Get(e, "creation_year"), Get(e, "jobs"), Get(e, "per_job_usd"), GoldReplay.Rows(e["installments"]))).ToList();
        return new BaseYearView(Get(d, "base_average_headcount"), Get(d, "per_job_usd"), Get(d, "tranche_years"), Get(d, "base_year_overridden"), Get(d, "high_water_mark_overridden"), events);
    }

    /// <summary>The five engine-grain tables of one pipeline call, from the C# engine's result over the recorded request. Python skipped scenarios its engine rejects.</summary>
    public static Dictionary<string, IReadOnlyList<GoldRow>> PipelineRows(PyDict call)
    {
        var args = (PyDict)call["args"]!;
        var scenario = (PyDict)args["scenario"]!;
        var (engineRows, payroll) = scenario.TryGetValue("dataset", out var name) ? Datasets.Value[(string)name!] : (null, GoldReplay.Rows(scenario["rows"]));
        using var request = JsonDocument.Parse(PyJson.Dumps(scenario, sortKeys: false, compact: true));
        var outcome = EngineRunner.Execute(request.RootElement, engineRows);
        var result = outcome.Ok ? (PyDict)outcome.Result! : throw new InvalidOperationException("the C# engine failed where Python's did not: " + outcome.Error);
        var client = GoldReplay.Int(args["client_id"]);
        var year = GoldReplay.Int(args["tax_year"]);
        var program = (string)args["program_code"]!;
        var method = (string)scenario["op"]!;
        var runId = (string)args["run_id"]!;
        var summary = GoldReplay.Rows(result["summary"]);
        var months = ((List<object?>)result["months"]!).Select(m => (object?)PyDate.FromIsoFormat((string)m!)).ToList();
        var run = new RunMethodResult(
            result["annual_average"], ((List<object?>)result["eligible_employees"]!).Count, ((List<object?>)result["total_hours_and_wages"]!).Count,
            ((List<object?>)result["employee_unit_matrix"]!).Count, GoldReplay.Rows(result["flags"]), months);
        return new Dictionary<string, IReadOnlyList<GoldRow>>
        {
            ["employee_period_fact"] = GoldProjection.EmployeePeriodFactRows(payroll, client, program, year, runId),
            ["employee_eligibility"] = GoldProjection.EmployeeEligibilityRows(GoldReplay.Rows(result["total_hours_and_wages"]), GoldReplay.Rows(result["all_averages"]), client, program, year, method, runId),
            ["onezero_matrix"] = GoldProjection.OneZeroMatrixRows(GoldReplay.Rows(result["employee_unit_matrix"]), client, program, year, method, runId),
            ["unit_month_summary"] = GoldProjection.UnitMonthSummaryRows(summary, client, year, method, runId, Longs(args["unreachable"])),
            ["run_method_summary"] = [GoldProjection.RunMethodSummaryRow(run, client, program, year, method, runId, GoldReplay.Int(args["unit_fein_rows"]), (PyDateTime)GoldReplay.Decode(args["appended_at"])!)],
        };
    }

    private static PyDict Pipeline(PyDict call)
    {
        var expected = call.TryGetValue("out", out var o) ? (PyDict)((PyDict)o!)["tables"]! : null;
        var tables = new PyDict();
        foreach (var (name, rows) in PipelineRows(call))
        {
            var full = expected is not null && ((PyDict)expected[name]!)["rows"] is not null;
            var tree = GoldReplay.Table(name, rows);
            var cells = (List<object?>)tree["rows"]!;
            var digest = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(PyJson.Dumps(cells, sortKeys: false, compact: true)))).ToLowerInvariant();
            tables.Add(name, new PyDict().Add("table", name).Add("columns", tree["columns"]).Add("n", (long)cells.Count).Add("digest", digest).Add("rows", full ? cells : null));
        }

        return new PyDict().Add("tables", tables);
    }

    private static Dictionary<string, (List<PayrollRow>, List<PyDict>)> LoadDatasets()
    {
        var result = new Dictionary<string, (List<PayrollRow>, List<PyDict>)>(StringComparer.Ordinal);
        foreach (var line in GoldenEngineTests.Lines("datasets.jsonl.gz"))
        {
            if (!line.StartsWith("{\"name\"", StringComparison.Ordinal))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            var tree = (PyDict)PyJson.Loads(line)!;
            result[doc.RootElement.GetProperty("name").GetString()!] = (EngineRunner.Rows(doc.RootElement.GetProperty("rows")), GoldReplay.Rows(tree["rows"]));
        }

        return result;
    }
}
