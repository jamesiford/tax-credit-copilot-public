using System.IO.Compression;
using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS3 (proximity family): replays every call of <c>parity/goldens/proximity.jsonl.gz</c> (production
/// <c>domain/calculation/proximity.py</c> on CPython 3.12) against <see cref="Proximity"/>. Trees are compared by type
/// (int versus float versus bool), key order, double bit pattern and exception type plus message.
/// </summary>
public sealed class ProximityParityTests
{
    private const string File = "proximity.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit()
    {
        var counts = new Dictionary<string, int>();
        var errors = 0;
        var failures = new List<string>();
        var total = 0;
        foreach (var call in Calls())
        {
            total++;
            var fn = (string)call["fn"]!;
            counts[fn] = counts.GetValueOrDefault(fn) + 1;
            var mismatch = Replay(call, out var wasError);
            errors += wasError ? 1 : 0;
            if (mismatch is not null && failures.Count < 8)
            {
                failures.Add($"#{call["id"]} {fn}: {mismatch}");
            }
            else if (mismatch is not null)
            {
                failures.Add(string.Empty);
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count}/{total} proximity calls diverged:\n" + string.Join("\n", failures.Where(f => f.Length > 0)));
        Assert.True(total > 10000 && errors > 500, $"corpus too thin: {total} calls, {errors} errors");
        foreach (var fn in new[] { "assess_employee", "fragility", "_rate", "near_miss_cohort", "fragile_cohort", "band_curve", "rest_of_year" })
        {
            Assert.True(counts.GetValueOrDefault(fn) > 30, fn + " is barely covered");
        }
    }

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison()
    {
        // Mutation self-test (in process): the same comparison, fed outputs with one deliberate defect, must disagree.
        var detected = new Dictionary<string, int> { ["ulp"] = 0, ["int-as-float"] = 0, ["tie-order"] = 0, ["key-order"] = 0, ["bool-flip"] = 0 };
        foreach (var call in Calls().Take(6000))
        {
            if (call.ContainsKey("err"))
            {
                continue;
            }

            var actual = Invoke(call);
            var expected = call["out"];
            foreach (var (name, mutate) in Perturbations)
            {
                var perturbed = mutate(Copy(actual));
                if (Compare(expected, perturbed, "$") is not null && !ReferenceEquals(perturbed, null))
                {
                    detected[name]++;
                }
            }
        }

        foreach (var (name, n) in detected)
        {
            Assert.True(n > 5, $"the comparison cannot fail for '{name}' ({n} detections)");
        }
    }

    [Fact]
    public void Max_binds_on_the_way_in_and_min_binds_on_the_way_out()
    {
        // 70 hrs/wk but $637/wk against a $636 floor: a thin wage cushion is the binding one when losing the job.
        var floors = new StatutoryFloors("GA_JTC", 2023, PyNumber.OfFloat(35.0), PyNumber.OfFloat(636.0), new PyDict(), new PyDict(), "ga_jtc.json");
        var row = new PyDict().Add("Employee_ID", "x").Add("total_hours", 3640L).Add("total_wages", 33124L).Add("weeks_worked", 52.0).Add("avg_weekly_hours", 70.0).Add("avg_weekly_wages", 637.0);
        var out_ = Proximity.Fragility(row, floors);
        Assert.Equal("wages", out_["binding_floor"]);
        Assert.True((double)out_["weekly_hours_to_lose"]! < 1.0);

        // 30 hrs at $15: both floors missed, the wage need (12.4) outranks the hours need (5.0).
        var miss = new PyDict().Add("Employee_ID", "y").Add("total_hours", 1560L).Add("total_wages", 23400L).Add("weeks_worked", 52.0).Add("avg_weekly_hours", 30.0).Add("avg_weekly_wages", 450.0);
        Assert.Equal(12.4, Proximity.AssessEmployee(miss, floors)["additional_weekly_hours"]);
    }

    private static readonly (string Name, Func<object?, object?> Apply)[] Perturbations =
    [
        ("ulp", t => Map(t, v => v is double d && double.IsFinite(d) && d != 0 ? BitConverter.Int64BitsToDouble(BitConverter.DoubleToInt64Bits(d) + 1) : v)),
        ("int-as-float", t => Map(t, v => v is long l ? (double)l : v)),
        ("bool-flip", t => Map(t, v => v is bool b ? !b : v)),
        ("tie-order", t => Map(t, v => v is List<object?> { Count: > 1 } list ? list.AsEnumerable().Reverse().ToList() : v)),
        ("key-order", t => Map(t, v => v is PyDict { Count: > 1 } d ? Reorder(d) : v)),
    ];

    private static PyDict Reorder(PyDict d)
    {
        var reversed = new PyDict();
        foreach (var kv in d.Reverse())
        {
            reversed.Add(kv.Key, kv.Value);
        }

        return reversed;
    }

    private static object? Map(object? t, Func<object?, object?> f) => t switch
    {
        PyDict d => f(d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, Map(kv.Value, f)))),
        List<object?> l => f(l.Select(x => Map(x, f)).ToList()),
        _ => f(t),
    };

    private static object? Copy(object? t) => Map(t, v => v);

    private static string? Replay(PyDict call, out bool wasError)
    {
        wasError = call.ContainsKey("err");
        try
        {
            var actual = Invoke(call);
            return wasError ? $"Python raised {call["err"]}: {call["msg"]} but C# returned a value" : Compare(call["out"], actual, "$");
        }
        catch (PyException e) when (wasError)
        {
            return e.PythonType == (string)call["err"]! && e.Message == (string)call["msg"]!
                ? null
                : $"exception: got {e.PythonType} '{e.Message}' expected {call["err"]} '{call["msg"]}'";
        }
        catch (PyException e)
        {
            return $"C# raised {e.PythonType} '{e.Message}' but Python returned a value";
        }
    }

    internal static object? Invoke(PyDict call)
    {
        var a = (PyDict)call["args"]!;
        switch ((string)call["fn"]!)
        {
            case "_rate":
                return Proximity.Rate(ToDouble(a["total_hours"]), ToDouble(a["total_wages"]));
            case "assess_employee":
                return Proximity.AssessEmployee(Row(a["average"]), Floors(a["floors"]), Decimals(a));
            case "fragility":
                return Proximity.Fragility(Row(a["average"]), Floors(a["floors"]), Decimals(a));
            case "near_miss_cohort":
                return Proximity.NearMissCohort(Rows(a["averages"]), Floors(a["floors"]), Within(a), Limit(a), Decimals(a), Population(a));
            case "fragile_cohort":
                return Proximity.FragileCohort(Rows(a["averages"]), Floors(a["floors"]), Within(a), Limit(a), Decimals(a), Population(a));
            case "band_curve":
                var bands = a.TryGetValue("bands", out var b) ? ((List<object?>)b!).Select(x => Number(x)).ToList() : null;
                return Proximity.BandCurve(Rows(a["averages"]), Floors(a["floors"]), bands, Decimals(a)).Cast<object?>().ToList();
            case "rest_of_year":
                var periods = ((List<object?>)a["periods"]!).Select(p => (PyDict)DecodeDates(p)!).ToList();
                var method = a.TryGetValue("method", out var m) ? (string?)m : "min_max";
                return Proximity.RestOfYear(periods, Floors(a["floors"]), DecodeDates(a["as_of"]), DecodeDates(a["year_end"]), method, Decimals(a));
            default:
                throw new PyUnsupportedException("unknown function " + call["fn"]);
        }
    }

    private static PyDict Row(object? o) => (PyDict)o!;

    private static List<PyDict> Rows(object? o) => ((List<object?>)o!).Cast<PyDict>().ToList();

    private static int Decimals(PyDict a) => a.TryGetValue("decimals", out var d) ? (int)(long)d! : 2;

    private static PyNumber? Within(PyDict a) => a.TryGetValue("within_weekly_hours", out var w) ? Number(w) : null;

    private static long? Limit(PyDict a) => a.TryGetValue("limit", out var l) ? (long?)l : null;

    private static PyDict? Population(PyDict a) => a.TryGetValue("population", out var p) ? (PyDict?)p : null;

    private static PyNumber Number(object? v) => v is long l ? PyNumber.OfInt(l) : PyNumber.OfFloat((double)v!);

    private static double ToDouble(object? v) => v is long l ? l : (double)v!;

    private static StatutoryFloors Floors(object? o)
    {
        var f = (PyDict)o!;
        var code = (string)f["program_code"]!;
        return new StatutoryFloors(code, (long)f["tax_year"]!, Number(f["min_hours"]), Number(f["min_wages"]), new PyDict(), new PyDict(), code.ToLowerInvariant() + ".json");
    }

    /// <summary>The exporter's tagged date <c>{"$date": "YYYY-MM-DD"}</c> becomes a <see cref="DateOnly"/>; containers are rebuilt.</summary>
    private static object? DecodeDates(object? t) => t switch
    {
        PyDict { Count: 1 } d when d.ContainsKey("$date") => PyDate.FromIsoFormat((string)d["$date"]!),
        PyDict d => d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, DecodeDates(kv.Value))),
        _ => t,
    };

    /// <summary>Returns the first difference between two trees, or <c>null</c> when they are identical in type, order and bits.</summary>
    private static string? Compare(object? expected, object? actual, string path)
    {
        switch (expected)
        {
            case null:
                return actual is null ? null : $"{path}: expected None, got {Show(actual)}";
            case bool b:
                return actual is bool ab && ab == b ? null : $"{path}: expected bool {b}, got {Show(actual)}";
            case long l:
                return actual is long al && al == l ? null : $"{path}: expected int {l}, got {Show(actual)}";
            case BigInteger bi:
                return actual is BigInteger abi && abi == bi ? null : $"{path}: expected int {bi}, got {Show(actual)}";
            case double d:
                return actual is double ad && PyFloat.SameBits(ad, d) ? null : $"{path}: expected float {PyFloat.Repr(d)}, got {Show(actual)}";
            case string s:
                return actual is string a && string.Equals(a, s, StringComparison.Ordinal) ? null : $"{path}: expected str '{s}', got {Show(actual)}";
            case List<object?> list:
                return CompareLists(list, actual, path);
            case PyDict dict:
                return CompareDicts(dict, actual, path);
            default:
                return $"{path}: unsupported expected type {expected.GetType().Name}";
        }
    }

    private static string? CompareLists(List<object?> expected, object? actual, string path)
    {
        if (actual is not List<object?> list || list.Count != expected.Count)
        {
            return $"{path}: expected list of {expected.Count}, got {Show(actual)}";
        }

        for (var i = 0; i < expected.Count; i++)
        {
            if (Compare(expected[i], list[i], $"{path}[{i}]") is { } diff)
            {
                return diff;
            }
        }

        return null;
    }

    private static string? CompareDicts(PyDict expected, object? actual, string path)
    {
        if (actual is not PyDict dict || !dict.Keys.SequenceEqual(expected.Keys))
        {
            return $"{path}: expected keys [{string.Join(",", expected.Keys)}], got {(actual is PyDict ad ? "[" + string.Join(",", ad.Keys) + "]" : Show(actual))}";
        }

        foreach (var kv in expected)
        {
            if (Compare(kv.Value, dict[kv.Key], $"{path}.{kv.Key}") is { } diff)
            {
                return diff;
            }
        }

        return null;
    }

    private static string Show(object? v) => v switch
    {
        null => "None",
        double d => "float " + PyFloat.Repr(d),
        long l => "int " + l,
        bool b => "bool " + b,
        string s => "str '" + s + "'",
        _ => v.GetType().Name,
    };

    private static IEnumerable<PyDict> Calls()
    {
        GoldenFiles.AssertOracleStamp(File);
        using var stream = System.IO.File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", File));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        _ = reader.ReadLine();
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            yield return (PyDict)PyJson.Loads(line)!;
        }
    }
}
