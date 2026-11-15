using System.Globalization;
using System.Numerics;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Differential fuzz of the rule-pack tools in the shipped world: <c>credit_math</c> (year packs, statutory floors, per-job amounts, entity combination),
/// <c>program_credit</c> (the program-keyed and state-keyed credit wrappers, <c>credit_from_pack</c>) and <c>pack_lookup</c>. Headcounts straddle each
/// pack's own minimum-new-jobs threshold by an ulp, half-cents and units; every program pack and tax year is asked for, missing years included
/// (they must fail loudly with Python's message); wages, priors, overrides and trails vary.
/// </summary>
internal sealed class CreditMathFuzz : FuzzFamily
{
    private static readonly string[] Codes = ["GA_JTC", "NY_EXCELSIOR", "SC_JTC", "NC_JTEC", "TN_JTC", "FL_QTI", "OH_JCTC", "CO_EZ", "VA_MBJF", "FED_WOTC"];
    private static readonly string[] States = ["GA", "NY", "SC", "NC", "TN", "FL", "OH", "CO", "VA"];

    private static readonly string[] Keys =
    [
        .. Codes, .. States, .. Codes.Take(4), .. States.Take(3), "TX", "XX", "ga", "Ga_Jtc", "ga_jtc", string.Empty, " GA", "NOPE", "Stra\u00dfe", "\u01c6", "\u0149", "\ufb01", "\u0131", "fed_wotc", "ZZ", "zz",
    ];

    private static readonly string[] PackFiles =
    [
        "ga_jtc.json", "ny_excelsior.json", "sc_jtc.json", "nc_jtec.json", "tn_jtc.json", "fl_qti.json", "oh_jctc.json", "co_ez.json", "va_mbjf.json", "federal_wotc_lite.json", string.Empty, ".json",
        "registry.json", "lookups.json", "schema.json", "methodology.json", "nope.json", "ga_jtc.json.json", "x.y.json", "ga_jtc.json",
    ];

    private static readonly object?[] Years = [null, 2018L, 2019L, 2020L, 2021L, 2022L, 2023L, 2024L, 2025L, 2026L, 2027L, 2030L, 0L, -1L, 2147483648L, 2023L, 2024L, 2025L];
    private static readonly object?[] Priors = [0.0, 0L, 1.0, 3.5, 40.0, 100.0, double.NaN, double.PositiveInfinity, -2.0, "7", null, 0.0, 0.0];
    private static readonly object?[] Overrides = [null, null, null, 0L, 0.0, 2.5, 3L, 10.0, -1.0, double.NaN, double.PositiveInfinity, 1e308, "2.5", string.Empty, new List<object?> { 1L }];
    private static readonly object?[] Wages = [null, null, 0.0, 52000.0, 51234.5678, 0.5, 1e12, -100.0, double.NaN, double.PositiveInfinity, 1e-300, 52000.0];
    private static readonly Lazy<List<PyDict>> Docs = new(LoadDocs);
    private static readonly Lazy<Dictionary<string, double>> MinJobs = new(LoadMinJobs);

    public override string Name => "credit_math";

    public override IReadOnlyList<string> Functions { get; } =
    [
        "apply_one_zero_program_credit", "apply_one_zero_state_credit", "program_per_job_usd", "state_per_job_usd", "combine_program_entity_credits", "combine_entity_credits",
        "credit_from_pack", "load_year_pack", "resolve_statutory_floors", "resolve_tax_year_convention", "authored_years", "is_year_scoped", "pack_file_for", "load_pack_one_zero",
    ];

    public override Func<PyDict, string?> CreateChecker()
    {
        var harness = new CreditMathHarness();
        return call => Replay(call, harness.Invoke) ?? WageMismatch(call, harness);
    }

    public override FamilyCase Generate(Rng r, string id)
    {
        var roll = r.Int(0, 99);
        var key = r.Pick(Keys);
        var shipped = new PyDict().Add("world", "shipped");
        var (fn, args) = roll switch
        {
            < 36 => ("apply_one_zero_program_credit", Apply(r, shipped, "apply_one_zero_program_credit", key)),
            < 46 => ("apply_one_zero_state_credit", Apply(r, shipped, "apply_one_zero_state_credit", key)),
            < 51 => ("program_per_job_usd", shipped.Add("key", key)),
            < 56 => ("state_per_job_usd", shipped.Add("key", key)),
            < 64 => ("combine_program_entity_credits", Combine(r, shipped, key)),
            < 70 => ("combine_entity_credits", Combine(r, shipped, key)),
            < 78 => ("credit_from_pack", FromPack(r, shipped)),
            < 85 => ("load_year_pack", YearPack(r, shipped)),
            < 91 => ("resolve_statutory_floors", shipped.Add("program_code", key).Add("tax_year", r.Pick(Years))),
            < 94 => ("resolve_tax_year_convention", shipped.Add("program_code", key).Add("tax_year", r.Pick(Years))),
            < 95 => ("authored_years", shipped.Add("pack_file", r.Pick(PackFiles))),
            < 96 => ("is_year_scoped", shipped.Add("pack_file", r.Pick(PackFiles))),
            < 98 => ("pack_file_for", shipped.Add("key", key)),
            _ => ("load_pack_one_zero", shipped.Add("key", key).Add("tax_year", r.Pick(Years)).Add("ingestion", null)),
        };
        return new FamilyCase(id, fn, args);
    }

    /// <summary>A year-pack request. The empty pack name with no year reads the rules folder itself, whose error is an OS-specific <c>PermissionError</c> with a machine path (the golden skips it too).</summary>
    private static PyDict YearPack(Rng r, PyDict args)
    {
        var file = r.Pick(PackFiles);
        var year = r.Pick(Years);
        return args.Add("pack_file", file).Add("tax_year", file.Length == 0 && year is null ? 2023L : year);
    }

    private static PyDict Apply(Rng r, PyDict args, string fn, string key)
    {
        var t = Threshold(key);
        object? avg = r.Chance(0.08)
            ? r.Pick(new object?[] { BigInteger.Pow(10, 20), BigInteger.Pow(10, 400), true, "14.5", "bad", null, string.Empty, new List<object?> { 1L }, double.NaN, double.PositiveInfinity, -3.5, 1e300, 5e-324 })
            : r.Int(0, 4) switch
            {
                0 => Pools.Around(r, t),
                1 => Pools.Around(r, t + r.Pick(new[] { 0.005, 0.015, 0.025, 0.125, 0.5, 1.0, 1.5, 12.0, 14.0 })),
                2 => r.Pick(new object[] { 0.0, -0.0, 0L, 1.0, 1.5, 2.0, 5.0, 10.125, 14L, 14.135, 14.145, 25.0, 50.0, 112.0, 120.5, 200.0, 1e6, 123456789.12345 }),
                3 => Pools.Around(r, r.Uniform(0, 300)),
                _ => Math.Round(r.Uniform(-5, 300), r.Pick(new[] { 0, 1, 2, 3, 10 })),
            };
        return args.Add("key", key).Add("average_headcount", avg).Add("prior", r.Chance(0.5) ? 0.0 : r.Pick(Priors)).Add("threshold_override", r.Pick(Overrides))
            .Add("wage_override", r.Pick(Wages)).Add("trail", Trail(r)).Add("fn", fn);
    }

    private static object? Trail(Rng r) => r.Chance(0.75)
        ? null
        : r.Pick(new object[] { new PyDict().Add("title", string.Empty).Add("citation", string.Empty), new PyDict().Add("title", "Pending").Add("citation", "c"), new PyDict().Add("title", "Custom").Add("citation", "x") });

    private static double Threshold(string key)
    {
        var code = key.Length == 2 ? Codes.FirstOrDefault(c => c.StartsWith(key, StringComparison.Ordinal)) : Codes.FirstOrDefault(c => string.Equals(c, key, StringComparison.OrdinalIgnoreCase));
        return code is not null && MinJobs.Value.TryGetValue(code, out var t) ? t : 2.0;
    }

    private static PyDict Combine(Rng r, PyDict args, string key)
    {
        var n = r.Pick(new[] { 0, 1, 2, 3, 5 });
        var fein = new PyDict();
        for (var i = 0; i < n; i++)
        {
            var name = r.Chance(0.1) ? r.Pick(new[] { string.Empty, "b", "a", "E\u00e9", "\U00010000" }) : $"E{i}";
            if (fein.ContainsKey(name))
            {
                continue;
            }

            object? value = r.Chance(0.06)
                ? r.Pick(new object?[] { 5L, new PyDict(), new PyDict().Add("average_headcount", null), new PyDict().Add("average_headcount", "15"), new PyDict().Add("average_headcount", double.NaN), new PyDict().Add("average_headcount", 1e300) })
                : new PyDict().Add("average_headcount", Pools.Around(r, r.Pick(new[] { 2.0, 5.0, 14.0, 30.0, 112.0, Threshold(key) })));
            fein.Add(name, value);
        }

        return args.Add("key", key).Add("fein_breakdown", fein).Add("trail", Trail(r)).Add("wage_override", r.Pick(Wages));
    }

    private static PyDict FromPack(Rng r, PyDict args)
    {
        var doc = r.Pick(Docs.Value);
        var thresholds = (PyDict)doc["thresholds"]!;
        var benefit = (PyDict)doc["benefit"]!;
        if (r.Chance(0.4))
        {
            doc = With(doc, "thresholds", With(thresholds, "minimum_new_jobs", r.Chance(0.5) ? Pools.Around(r, Convert.ToDouble(thresholds["minimum_new_jobs"], CultureInfo.InvariantCulture)) : r.Pick(Overrides)));
        }

        if (r.Chance(0.4))
        {
            doc = With(doc, "benefit", With(benefit, r.Chance(0.5) ? "amount_per_qualifying_job_usd" : "benefit_period_years", r.Pick(new object?[] { 5L, 5.0, 0L, -1L, 3500.5, 2999.99, 1e16, null, "5", double.NaN, 1L, 2L })));
        }

        var names = r.Pick(new[] { new[] { "GA_JTC", "GA", "ga_jtc.json" }, ["zy_draft_jtc", "ZY", "x.json"], ["ZL_PCT", "ZL", "zl_pct.json"], [string.Empty, string.Empty, string.Empty] });
        var avg = r.Pick(new object[] { 14.0, 112.0, 0.0, 3.5, 1e6, 80L, double.NaN, Pools.Around(r, 2.0) });
        return args.Add("label", "fuzz").Add("doc", doc).Add("names", names.Select(n => (object?)n).ToList()).Add("average_headcount", avg)
            .Add("prior", r.Pick(new object[] { 0.0, 100.0, 1.5, 5.0, 30L })).Add("threshold_override", r.Pick(new object?[] { null, null, 0.5, 2.5 })).Add("trail", Trail(r)).Add("wage_override", 51234.5678);
    }

    private static PyDict With(PyDict d, string key, object? value) => d.ContainsKey(key)
        ? d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, kv.Key == key ? value : kv.Value))
        : d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, kv.Value)).Add(key, value);

    private static List<PyDict> LoadDocs()
    {
        var found = new List<PyDict>();
        foreach (var file in Directory.EnumerateFiles(CreditMathHarness.RulesDirectory, "*.json", SearchOption.TopDirectoryOnly))
        {
            if (PyJson.Loads(File.ReadAllText(file)) is PyDict d && d.TryGetValue("benefit", out var b) && b is PyDict && d.TryGetValue("thresholds", out var t) && t is PyDict tp && tp.ContainsKey("minimum_new_jobs") && d.ContainsKey("credit"))
            {
                found.Add(d);
            }
        }

        return found;
    }

    private static Dictionary<string, double> LoadMinJobs()
    {
        var map = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var code in Codes)
        {
            var file = Path.Combine(CreditMathHarness.RulesDirectory, code.ToLowerInvariant() + ".json");
            if (!File.Exists(file))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(File.ReadAllText(file));
            if (doc.RootElement.TryGetProperty("thresholds", out var t) && t.TryGetProperty("minimum_new_jobs", out var m) && m.ValueKind == JsonValueKind.Number)
            {
                map[code] = m.GetDouble();
            }
        }

        return map;
    }

    private static string? WageMismatch(PyDict call, CreditMathHarness harness)
    {
        if (call.ContainsKey("err") || !((PyDict)call["args"]!).TryGetValue("wage_calls", out var expected))
        {
            return null;
        }

        return ClaimGolden.Compare(expected, harness.LastWageCalls, "$.wage_calls");
    }
}
