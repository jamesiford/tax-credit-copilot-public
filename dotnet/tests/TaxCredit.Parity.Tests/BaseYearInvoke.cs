using System.IO.Compression;
using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pilot;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Parity.Tests;

/// <summary>Replays one call of <c>baseyear.jsonl.gz</c> against the C# port, returning the tree shape the exporter recorded.</summary>
internal static class BaseYearInvoke
{
    public const string File = "baseyear.jsonl.gz";

    private static readonly Lazy<Dictionary<string, DesignationRegistry>> Registries = new(LoadRegistries);
    private static readonly Lazy<Dictionary<string, RuleLibrary>> Worlds = new(() =>
        ((PyDict)Meta()["worlds"]!).ToDictionary(kv => kv.Key, kv => new RuleLibrary(new OverlayRulePackSource((PyDict)kv.Value!)), StringComparer.Ordinal));

    public static object? Invoke(PyDict call)
    {
        var a = (PyDict)call["args"]!;
        switch ((string)call["fn"]!)
        {
            case "compute_base_year_tranches":
                return Traced(a, () => Tree(Compute(a)), merge: true);
            case "tranche_columns":
                return Columns(UnitTrendTools.TrancheColumns(Compute(a), Longs(a["years"])));
            case "aggregate_units":
                return Columns(UnitTrendTools.AggregateUnits(Rows(a["rows"])));
            case "build_unit_series":
                return Series(UnitTrendTools.BuildUnitSeries(PerYear(a["per_year"])));
            case "infer_base_year":
                return UnitTrendTools.InferBaseYear(UnitYears(a["unit_years"]), a["reachable"] is null ? null : Reachable(a["reachable"]));
            case "unit_status":
                return Status(a);
            case "unit_trend":
                return Traced(a, () => Tree(Trend(a)), merge: true);
            case "unit_trend_columns":
                return Columns(UnitTrendTools.TrancheColumns(Trend(a), Enumerable.Range(0, 10).Select(i => (long)a["base_year"]! - 1 + i).ToList()));
            case "detect_designation_splits":
                return Splits(a);
            case "detect_designation_splits_trail":
                return Traced(a, () => Splits(a), merge: false);
            case "designation_history":
                return Columns(Registries.Value[(string)a["registry"]!].History((string)a["unit_id"]!, (long?)a["client_id"]));
            case "_designation_at":
                return Registries.Value[(string)a["registry"]!].DesignationAt((string)a["unit_id"]!, (long)a["tax_year"]!, (long?)a["client_id"]);
            case "all_designations":
                return Registries.Value[(string)a["registry"]!].All();
            case "disc_meta":
                return DesignationRegistry.DiscMeta();
            case "negotiated_session":
                return Negotiated((List<object?>)a["ops"]!);
            case "reconcile":
                return Reconcile(a);
            case "_MIN_REACHABLE_MONTHS":
                return (long)UnitTrendQueryHelpers.MinReachableMonths;
            case "_candidate_years":
                return UnitTrendQueryHelpers.CandidateYears(Worlds.Value[(string)a["world"]!], (string)a["state_or_program"]!).Select(y => (object?)y).ToList();
            case "_year_benefit":
                return UnitTrendQueryHelpers.YearBenefit(Worlds.Value[(string)a["world"]!], (string)a["program_code"]!, (long?)a["tax_year"]);
            default:
                throw new PyUnsupportedException("unknown function " + call["fn"]);
        }
    }

    private static PyDict Meta()
    {
        GoldenFiles.AssertOracleStamp(File);
        using var stream = System.IO.File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", File));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        return (PyDict)PyJson.Loads(reader.ReadLine()!)!;
    }

    private static Dictionary<string, DesignationRegistry> LoadRegistries() =>
        ((PyDict)Meta()["registries"]!).ToDictionary(kv => kv.Key, kv => Registry((PyDict)kv.Value!), StringComparer.Ordinal);

    private static DesignationRegistry Registry(PyDict spec)
    {
        var synthetic = (bool)spec["synthetic"]!;
        var legacy = ((List<object?>)spec["legacy"]!).Cast<List<object?>>()
            .Select(p => new KeyValuePair<string, IReadOnlyList<PyDict>>((string)p[0]!, Rows(p[1]))).ToList();
        var source = ((List<object?>)spec["source"]!).Cast<List<object?>>().Select(p => new SourceDesignation((long)p[0]!, (string)p[1]!, Rows(p[2]))).ToList();
        return new DesignationRegistry(legacy, source, Rows(spec["synthetic_default"]), () => synthetic);
    }

    private static List<PyDict> Rows(object? v) => ((List<object?>)v!).Cast<PyDict>().ToList();

    private static List<long> Longs(object? v) => ((List<object?>)v!).Select(x => (long)x!).ToList();

    private static PyNumber Num(object? v) => v switch
    {
        long l => PyNumber.OfInt(l),
        double d => PyNumber.OfFloat(d),
        _ => throw new PyUnsupportedException("a number argument of type " + v?.GetType().Name),
    };

    private static PyNumber? MaybeNum(object? v) => v is null ? null : Num(v);

    private static IEnumerable<(long Year, object? Value)> Pairs(object? v) =>
        ((List<object?>)v!).Cast<List<object?>>().Select(p => ((long)p[0]!, p[1]));

    private static OrderedMap<long, PyNumber> Yearly(object? v) =>
        Pairs(v).Aggregate(new OrderedMap<long, PyNumber>(), (m, p) => m.Set(p.Year, Num(p.Value)));

    private static OrderedMap<long, YearBenefit>? Benefit(object? v) => v is null
        ? null
        : Pairs(v).Aggregate(new OrderedMap<long, YearBenefit>(), (m, p) =>
        {
            var d = (PyDict)p.Value!;
            return m.Set(p.Year, new YearBenefit(d.TryGetValue("threshold", out var t) ? Num(t) : null, d.TryGetValue("per_job_usd", out var j) ? Num(j) : null));
        });

    private static BaseYearSettings Settings(PyDict a) => new(
        Num(a["threshold"]), Num(a["per_job_usd"]), a["tranche_years"] is long t ? t : BaseYearEngine.DefaultTrancheYears,
        MaybeNum(a.TryGetValue("base_average_override", out var bo) ? bo : null), MaybeNum(a.TryGetValue("high_water_mark_override", out var ho) ? ho : null),
        Benefit(a["benefit"]));

    internal static BaseYearResult Compute(PyDict a) =>
        BaseYearEngine.ComputeBaseYearTranches((string)a["state"]!, Yearly(a["yearly"]), (long)a["base_year"]!, Settings(a));

    private static OrderedMap<long, PyDict> UnitYears(object? v) =>
        Pairs(v).Aggregate(new OrderedMap<long, PyDict>(), (m, p) => m.Set(p.Year, (PyDict)p.Value!));

    private static OrderedMap<long, long> Reachable(object? v) =>
        Pairs(v).Aggregate(new OrderedMap<long, long>(), (m, p) => m.Set(p.Year, (long)p.Value!));

    private static OrderedMap<long, IReadOnlyList<PyDict>> PerYear(object? v) =>
        Pairs(v).Aggregate(new OrderedMap<long, IReadOnlyList<PyDict>>(), (m, p) => m.Set(p.Year, Rows(p.Value)));

    private static BaseYearResult Trend(PyDict a) => UnitTrendTools.UnitTrend(UnitYears(a["unit_years"]), (string)a["state"]!, (long)a["base_year"]!, Settings(a));

    private static PyDict Tree(BaseYearResult r) => new PyDict()
        .Add("result", r.ToFields()).Add("dict", r.ToDict())
        .Add("totals", new List<object?> { PyNum.IntTree(r.TotalAnnualCreditUsd), PyNum.IntTree(r.TotalTrancheLifetimeUsd) });

    private static string Status(PyDict a) => UnitTrendTools.UnitStatus(
        (long)a["tax_year"]!, (long?)a["base_year"], (bool)a["qualified"]!, (long)a["months_with_headcount"]!,
        a["months_reachable"] is long m ? m : UnitTrendTools.MonthsInYear);

    private static List<object?> Columns(IEnumerable<PyDict> rows) => rows.Select(r => (object?)r).ToList();

    private static PyDict Series(OrderedMap<string, OrderedMap<long, PyDict>> series) => series.Aggregate(new PyDict(), (d, kv) =>
        d.Add(kv.Key, kv.Value.Aggregate(new PyDict(), (inner, y) => inner.Add(y.Key.ToString(System.Globalization.CultureInfo.InvariantCulture), y.Value))));

    private static PyDict Splits(PyDict a) => Registries.Value[(string)a["registry"]!].DetectDesignationSplits(
        (string)a["state"]!, (long)a["tax_year"]!, a["base_year"] is long b ? b : DesignationRegistry.DefaultBaseYear);

    private static PyDict Reconcile(PyDict a) => BenchmarkReconciliation.Reconcile(
        Rows(a["benchmark"]), Rows(a["computed"]), a.TryGetValue("key", out var k) ? (string)k! : "key", a.TryGetValue("value", out var v) ? (string)v! : "average_headcount",
        a.TryGetValue("tolerance", out var t) ? Num(t) : null);

    /// <summary>Runs <paramref name="body"/> under the trail recorder the arguments ask for; the result is merged with or wrapped beside the trail like Python's.</summary>
    private static object? Traced(PyDict a, Func<object?> body, bool merge)
    {
        if (a["trail"] is not PyDict spec)
        {
            return body();
        }

        var recorder = new TrailRecorder((string)spec["title"]!, (string)spec["citation"]!);
        object? result;
        using (TrailContext.Use(recorder))
        {
            result = body();
        }

        if (merge)
        {
            return ((PyDict)result!).Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value)).Add("trail", recorder.ToDict());
        }

        return new PyDict().Add("result", result).Add("trail", recorder.ToDict());
    }

    private static List<object?> Negotiated(List<object?> ops)
    {
        var now = DateTime.UnixEpoch;
        var store = new NegotiatedOverrides(() => now);
        var steps = new List<object?>();
        foreach (var step in ops.Cast<List<object?>>())
        {
            var op = (string)step[0]!;
            var a = (PyDict)step[1]!;
            try
            {
                if (op == "register")
                {
                    now = Instant(Longs(a["now"]));
                }

                steps.Add(new PyDict().Add("op", op).Add("out", Step(store, op, a)));
            }
            catch (PyException e)
            {
                steps.Add(new PyDict().Add("op", op).Add("err", e.PythonType).Add("msg", e.Message));
            }
        }

        return steps;
    }

    private static DateTime Instant(List<long> p) =>
        new DateTime((int)p[0], (int)p[1], (int)p[2], (int)p[3], (int)p[4], (int)p[5], DateTimeKind.Utc).AddTicks(p[6] * 10);

    private static PyDict? Step(NegotiatedOverrides store, string op, PyDict a)
    {
        switch (op)
        {
            case "register":
                return store.Register(
                    (string)a["state"]!, (string?)Opt(a, "worksite_id"), MaybeNum(Opt(a, "wage_standard_weekly")), MaybeNum(Opt(a, "min_jobs")),
                    a.ContainsKey("source") ? (string)a["source"]! : "self_service", (long?)Opt(a, "effective_years"), (string?)Opt(a, "note"));
            case "resolve":
                return a.ContainsKey("worksite") ? store.Resolve((string)a["state"]!, (string?)a["worksite"]) : store.Resolve((string)a["state"]!);
            default:
                return store.List();
        }
    }

    private static object? Opt(PyDict a, string key) => a.TryGetValue(key, out var v) ? v : null;
}
