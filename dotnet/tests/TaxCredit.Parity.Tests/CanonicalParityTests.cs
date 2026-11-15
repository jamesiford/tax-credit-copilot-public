using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Payroll;

namespace TaxCredit.Parity.Tests;

/// <summary>The hooks of one golden call: the ingested-config port and the worksite registry, rebuilt from the call's own arguments.</summary>
internal sealed class CallHooks(PyDict args) : IIngestedConfigSource, IWorksiteRegistry
{
    private readonly PyDict? _ingested = args.TryGetValue("ingested", out var i) ? (PyDict?)i : null;

    /// <inheritdoc />
    public IReadOnlyList<object?> Sites { get; } = args.TryGetValue("sites", out var s)
        ? ((List<object?>)s!).Select(e => e is string ? new object() : e).ToList()
        : [];

    /// <inheritdoc />
    public object? Load(string program)
    {
        if (_ingested is null || !_ingested.TryGetValue(program, out var v))
        {
            return null;
        }

        return v is PyDict d && d.ContainsKey("$raise") ? throw new InvalidOperationException("ingestion source down") : v;
    }
}

/// <summary>
/// Gate DS7 (ingestion family, canonical mapping): replays every call of <c>parity/goldens/canonical.jsonl.gz</c> (production <c>tools/canonical.py</c>,
/// CPython 3.12) against <see cref="CanonicalMapper"/>, <see cref="PayCodeClassifier"/> and the infrastructure <see cref="PayPeriodCsvAdapter"/>.
/// Trees are compared by type (int versus float), key order, double bit pattern and exception type plus message.
/// </summary>
public sealed class CanonicalParityTests
{
    private const string File = "canonical.jsonl.gz";
    private static readonly string[] Functions = ["to_canonical", "to_canonical_csv", "collapse_to_employee_period", "_infer_frequency", "_pay_code_classifier", "_is_includable", "_worksite_join", "csv_rows"];

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() => ClaimGolden.AssertAllMatch(File, Invoke, Functions, 1500, 10);

    [Fact]
    public void A_pay_line_of_an_ingested_inclusion_list_is_the_only_one_that_counts()
    {
        // test_canonical.test_pay_code_classification_excludes_non_taxable, through the C# entry points.
        var rows = new RowsAdapter([Row("Regular"), Row("Mileage"), Row("Bonus")]);
        var mapper = new CanonicalMapper();
        var records = mapper.ToCanonical(rows, 2025);
        Assert.Equal([true, false, true], records.Select(r => r.Includable));
        Assert.Single(CanonicalMapper.CollapseToEmployeePeriod(records));
    }

    [Fact]
    public void The_registry_of_site_objects_never_matches_so_every_worksite_gets_the_placeholder()
    {
        // CQ-01: production's SITES holds Site dataclass instances, which have no .get.
        var join = new CanonicalMapper(null, new CallHooks(new PyDict().Add("sites", new List<object?> { "$object" }))).WorksiteJoin("GA_ATL_HQ");
        Assert.Equal((null, "GA_ATL_HQ"), join);
    }

    private object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        var hooks = new CallHooks(a);
        var mapper = new CanonicalMapper(hooks, a.ContainsKey("sites") ? hooks : null);
        return fn switch
        {
            "to_canonical" => mapper.ToCanonical(new RowsAdapter(IngestionGolden.Rows(a["rows"])), TaxYear(a), Program(a)).Select(r => (object?)r.ToTree()).ToList(),
            "to_canonical_csv" => CsvDigest(mapper, a),
            "collapse_to_employee_period" => CanonicalMapper.CollapseToEmployeePeriod(((List<object?>)a["records"]!).Select(IngestionGolden.Record)).Cast<object?>().ToList(),
            "_infer_frequency" => CanonicalMapper.InferFrequency(IngestionGolden.Date(a["start"]), IngestionGolden.Date(a["end"])),
            "_pay_code_classifier" => Classifier(a, hooks),
            "_is_includable" => new PayCodeClassifier(Set(a["included"]), Set(a["excluded"])!).IsIncludable((string)a["pay_code"]!),
            "_worksite_join" => Join(mapper, (string)a["worksite_id"]!),
            "csv_rows" => CsvRows(a),
            _ => throw new PyUnsupportedException("unknown function " + fn),
        };
    }

    private static long? TaxYear(PyDict a) => a.TryGetValue("tax_year", out var v) ? (long?)v : null;

    private static string Program(PyDict a) => a.TryGetValue("program", out var v) ? (string)v! : "GA_JTC";

    private static HashSet<string>? Set(object? v) => v is List<object?> l ? l.Cast<string>().ToHashSet(StringComparer.Ordinal) : null;

    private static List<object?> Sorted(IEnumerable<string> set) => PySort.Sorted(set, s => s, PyStr.Comparer).Cast<object?>().ToList();

    private static List<object?> Classifier(PyDict a, CallHooks hooks)
    {
        var c = PayCodeClassifier.For((string)a["program"]!, hooks);
        return [c.Included is null ? null : Sorted(c.Included), Sorted(c.Excluded)];
    }

    private static PyDict Join(CanonicalMapper mapper, string worksiteId)
    {
        var (address, unit) = mapper.WorksiteJoin(worksiteId);
        return new PyDict().Add("worksite_address", address).Add("unit_number", unit);
    }

    private static PyDict CsvDigest(CanonicalMapper mapper, PyDict a)
    {
        var records = mapper.ToCanonical(new PayPeriodCsvAdapter(IngestionGolden.PayrollCsv), TaxYear(a), Program(a));
        var trees = records.Select(r => (object?)r.ToTree()).ToList();
        return new PyDict().Add("$digest", IngestionGolden.Sha256(trees)).Add("n", (long)trees.Count).Add("head", trees.Take(2).ToList());
    }

    private static List<object?> CsvRows(PyDict a)
    {
        var path = Path.Combine(AppContext.BaseDirectory, "canonical-csv-" + Guid.NewGuid().ToString("N")[..8] + ".csv");
        try
        {
            if (!a.ContainsKey("missing"))
            {
                System.IO.File.WriteAllBytes(path, new System.Text.UTF8Encoding(false).GetBytes((string)a["text"]!));
            }

            return new PayPeriodCsvAdapter(path).Rows().Cast<object?>().ToList();
        }
        finally
        {
            System.IO.File.Delete(path);
        }
    }

    private static PyDict Row(string code) => new PyDict()
        .Add("Employee_ID", "E1").Add("Worksite_ID", "GA_A").Add("Pay_Period_Start", "2025-01-15").Add("Pay_Period_End", "2025-01-28")
        .Add("Pay_Date", "2025-02-02").Add("Hours_Worked", "10").Add("Gross_Wages", "100").Add("Pay_Code", code);
}
