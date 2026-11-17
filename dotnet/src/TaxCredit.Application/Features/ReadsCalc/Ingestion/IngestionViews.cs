using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Qc;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Ingestion;

/// <summary>Shows each deterministic ingestion stage without confusing a raw source read with an accepted run.</summary>
public sealed partial class IngestionViews(IClientPayrollSource source, CanonicalMapper canonical, RuleLibrary library,
    QcAnnotations annotations, IClock clock)
{
    private static readonly string[] Agents = ["PayrollIngestAgent", "ExceptionReportAgent"];
    private static readonly string[] SourceFields =
    [
        "Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
        "Tax_Year", "Hours_Worked", "Gross_Wages", "Pay_Code",
    ];
    /// <summary>The fiscal selection, canonical stages and exception annotations all describe the same source.</summary>
    public object Overview(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var state = args.Text("state", "GA")!.ToUpperInvariant();
        var year = args.WholeNumber("tax_year");
        var client = args.Client();
        var rows = PayrollRows.RequirePayPeriods(source, annotations.Resolutions(client), accountId: client);
        var stateRows = rows.Where(row => Text(row.Get("Worksite_ID")).StartsWith(state + "_", StringComparison.Ordinal)).ToArray();
        var window = Window(client, year, state);
        var selected = window is null ? rows : rows.Where(row => InWindow(row.PayDateText(), window)).ToArray();
        var recs = canonical.ToCanonical(new Adapter(selected), program: state + "_JTC")
            .Where(record => record.WorksiteId.StartsWith(state + "_", StringComparison.Ordinal)).ToArray();
        var includable = recs.Where(record => record.Includable).ToArray();
        var periods = CanonicalMapper.CollapseToEmployeePeriod(recs);
        var qc = QcDetector.RunExceptionReport(rows.Select(row => row.Dict).ToArray(), year, state);
        var decisions = annotations.Resolutions(client).Items.ToDictionary(item => item.Key, item => item.Value, StringComparer.Ordinal);
        var exceptions = ((IEnumerable<object?>)qc["test_of_twos"]!).Concat((IEnumerable<object?>)qc["meaningful_pay_period"]!).Cast<PyDict>()
            .Select(anomaly => Enrich(anomaly, decisions)).ToArray();
        var summary = (PyDict)qc["summary"]!;
        summary.Set("unresolved", (long)exceptions.Count(row => row["resolution"] is null));
        var excluded = stateRows.Length - selected.Count(row => Text(row.Get("Worksite_ID")).StartsWith(state + "_", StringComparison.Ordinal));
        var note = window is null ? $"no fiscal rule resolved for {year}; all rows carried forward"
            : $"{Iso(window.Begin)} to {Iso(window.End)}, read from the client's own fiscal rule; {excluded} excluded because the paycheck fell outside the fiscal year";
        return Map(("as_of", Iso(DateOnly.FromDateTime(clock.UtcNow.UtcDateTime))), ("tax_year", year), ("state", state),
            ("automation", Map(("agents", Agents),
                ("note", "Ingestion is agent-automated; the numbers below are deterministic. The human validates exceptions and corrections — the agent never drops a record."))),
            ("field_map", FieldMap), ("raw_sample", stateRows.Take(12).Select(Raw).ToArray()),
            ("pipeline", new[]
            {
                Stage("Source rows (all years)", stateRows.Length, $"raw BCS pay-period rows for {state}"),
                Stage("Selected by fiscal window (BA-01)", recs.Length, note),
                Stage("Includable after pay-code filter (DATA-05)", includable.Length, $"{recs.Length - includable.Length} non-wage lines suppressed (mileage / reimbursement)"),
                Stage("Collapsed to employee×pay-period", periods.Count, "one record per employee per pay period"),
            }), ("totals", Map(("source_rows", stateRows.Length), ("fiscal_year_rows", recs.Length), ("includable_rows", includable.Length),
                ("excluded_rows", recs.Length - includable.Length), ("employee_periods", periods.Count),
                ("distinct_employees", recs.Select(record => record.EmployeeId).Distinct().Count()),
                ("distinct_worksites", recs.Select(record => record.WorksiteId).Distinct().Count()))),
            ("pay_code_split", recs.GroupBy(record => record.PayCode).OrderBy(group => group.Key, PyStr.Comparer)
                .Select(group => Map(("pay_code", group.Key), ("count", group.Count()))).ToArray()),
            ("qc", Map(("summary", summary), ("thresholds", qc["thresholds"]), ("exceptions", exceptions))));
    }

    private FiscalWindow? Window(long? client, int year, string state)
    {
        var code = state + "_JTC";
        var file = library.CodeToPack.Items().FirstOrDefault(item => item.Key == code).Value;
        if (file is null || !library.AuthoredYears(file).Contains(year))
        {
            return null;
        }
        var convention = Text(library.ResolveTaxYearConvention(code, year)["label"]);
        return source.ClientFiscalWindow(client, year, convention);
    }

    private static Dictionary<string, object?> Enrich(PyDict anomaly, Dictionary<string, PyDict> decisions)
    {
        var output = (Dictionary<string, object?>)Transport(anomaly)!;
        var id = QcResolutions.ExceptionId(anomaly);
        output["exception_id"] = id;
        output["resolution"] = decisions.GetValueOrDefault(id);
        if (output.GetValueOrDefault("units") is object?[] units)
        {
            foreach (var unit in units.Cast<Dictionary<string, object?>>())
            {
                unit["worksite_name"] = SiteLabels.Name(Text(unit.GetValueOrDefault("worksite_id")));
            }
        }
        if (output.TryGetValue("worksite_id", out var site))
        {
            output["worksite_name"] = SiteLabels.Name(Text(site));
        }
        return output;
    }

    private static Dictionary<string, object?> Stage(string name, int count, string note) => Map(("stage", name), ("count", count), ("note", note));

    private static bool InWindow(string day, FiscalWindow window) =>
        string.CompareOrdinal(Iso(window.Begin), day[..10]) <= 0 && string.CompareOrdinal(day[..10], Iso(window.End)) <= 0;

    private static Dictionary<string, object?> Raw(PayRow row) =>
        SourceFields.ToDictionary(key => key, key => key == "Pay_Code" ? row.Get(key) ?? "Regular" : row.Get(key), StringComparer.Ordinal);

    private sealed class Adapter(IReadOnlyList<PayRow> rows) : ISourceAdapter
    {
        public IEnumerable<PyDict> Rows() => rows.Select(row => row.Dict);
    }
}
