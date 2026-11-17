using System.IO.Compression;
using System.Numerics;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Shared plumbing of the claims-family golden replays: reading goldens, decoding the tagged JSON values, and the bit-exact tree comparison.</summary>
internal static class ClaimGolden
{
    /// <summary>Streams every call line of a golden (the meta line is skipped, after the oracle stamp is checked).</summary>
    public static IEnumerable<PyDict> Calls(string file)
    {
        GoldenFiles.AssertOracleStamp(file);
        using var stream = File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", file));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        _ = reader.ReadLine();
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            yield return (PyDict)PyJson.Loads(line)!;
        }
    }

    /// <summary>Runs one call and returns the first difference from Python's record (a value or an exception), or <c>null</c> when identical.</summary>
    public static string? Replay(PyDict call, Func<PyDict, object?> invoke, out bool wasError)
    {
        wasError = call.ContainsKey("err");
        try
        {
            var actual = invoke(call);
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

    /// <summary>Replays every call, asserts none diverged and that each function in <paramref name="functions"/> is well covered.</summary>
    public static void AssertAllMatch(string file, Func<PyDict, object?> invoke, string[] functions, int minimumCalls, int minimumErrors)
    {
        var counts = new Dictionary<string, int>();
        var failures = new List<string>();
        var total = 0;
        var errors = 0;
        foreach (var call in Calls(file))
        {
            total++;
            var fn = (string)call["fn"]!;
            counts[fn] = counts.GetValueOrDefault(fn) + 1;
            var mismatch = Replay(call, invoke, out var wasError);
            errors += wasError ? 1 : 0;
            if (mismatch is not null)
            {
                failures.Add(failures.Count < 8 ? $"#{call["id"]} {fn}: {mismatch}" : string.Empty);
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count}/{total} calls of {file} diverged:\n" + string.Join("\n", failures.Where(f => f.Length > 0)));
        Assert.True(total >= minimumCalls && errors >= minimumErrors, $"corpus too thin: {total} calls, {errors} errors");
        foreach (var fn in functions)
        {
            Assert.True(counts.GetValueOrDefault(fn) > 5, fn + " is barely covered");
        }
    }

    /// <summary>The claim fields of a golden spec as a <see cref="ClaimSpec"/> (absent keys are Python defaults).</summary>
    public static ClaimSpec Spec(object? tree)
    {
        var s = (PyDict)tree!;
        return new ClaimSpec
        {
            ClientId = (long)s["client_id"]!,
            ProgramCode = Get<string>(s, "program_code"),
            TaxYear = Get<long?>(s, "tax_year"),
            Status = s.TryGetValue("status", out var st) ? ClaimEnumExtensions.StatusFromValue((string)st!) : ClaimStatus.NotAssessed,
            Provenance = s.TryGetValue("provenance", out var pv) ? ClaimEnumExtensions.ProvenanceFromValue((string)pv!) : Provenance.Computed,
            IdentifiedUsd = Raw(s, "identified_usd"),
            ClaimedUsd = Raw(s, "claimed_usd"),
            CertifiedUsd = Raw(s, "certified_usd"),
            AverageHeadcount = Get<double?>(s, "average_headcount"),
            BaseAverageHeadcount = Get<double?>(s, "base_average_headcount"),
            ThresholdJobs = Get<double?>(s, "threshold_jobs"),
            IsBaseYear = s.TryGetValue("is_base_year", out var by) && (bool)by!,
            EntityId = Get<long?>(s, "entity_id"),
            IdentifiedRunId = Get<string>(s, "identified_run_id"),
            AssumptionSetId = Get<string>(s, "assumption_set_id"),
            RulePackVersion = Get<string>(s, "rule_pack_version"),
            FiledOn = Date(s, "filed_on"),
            FilingReference = Get<string>(s, "filing_reference"),
            DecidedBy = Get<string>(s, "decided_by"),
            DecidedAt = DateTimeOf(s, "decided_at"),
            DeclineReason = Get<string>(s, "decline_reason"),
            ClaimId = Get<string>(s, "claim_id"),
            EffectiveFrom = DateTimeOf(s, "effective_from"),
            EffectiveTo = DateTimeOf(s, "effective_to"),
        };
    }

    /// <summary>The value under <paramref name="key"/> as a money input: a tagged decimal becomes a <see cref="PyDecimal"/>, anything else stays raw.</summary>
    public static object? Raw(PyDict s, string key) => s.TryGetValue(key, out var v) ? Untag(v) : null;

    /// <summary>Decodes a <c>{"$dec": ...}</c> tag; other values pass through.</summary>
    public static object? Untag(object? v) => v is PyDict { Count: 1 } d && d.TryGetValue("$dec", out var text) ? PyDecimal.Parse((string)text!) : v;

    /// <summary>The decimal of a tagged argument.</summary>
    public static PyDecimal Decimal(object? v) => (PyDecimal)Untag(v)!;

    /// <summary>A typed optional field (<c>null</c> when absent or <c>None</c>).</summary>
    public static T? Get<T>(PyDict s, string key) => s.TryGetValue(key, out var v) && v is not null ? (T)v : default;

    /// <summary>A <c>{"$date": ...}</c> field.</summary>
    public static DateOnly? Date(PyDict s, string key) =>
        s.TryGetValue(key, out var v) && v is PyDict d ? PyDate.FromIsoFormat((string)d["$date"]!) : null;

    /// <summary>A <c>{"$dt": ...}</c> field.</summary>
    public static PyDateTime? DateTimeOf(PyDict s, string key) =>
        s.TryGetValue(key, out var v) && v is PyDict d ? PyDateTime.FromIsoFormat((string)d["$dt"]!) : null;

    /// <summary>The first difference between two trees, or <c>null</c> when they agree in type (int, float, bool), key order, double bits and text.</summary>
    public static string? Compare(object? expected, object? actual, string path)
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
}
