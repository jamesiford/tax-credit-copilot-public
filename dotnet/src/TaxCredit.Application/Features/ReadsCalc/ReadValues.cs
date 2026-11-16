using System.Collections;
using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Adapts canonical computation trees to transport objects, never using the evidence serializer for HTTP.</summary>
public static class ReadValues
{
    /// <summary>Preserves nulls, numeric values and scale-bearing money while turning ordered engine mappings into JSON objects.</summary>
    public static object? Transport(object? value) => value switch
    {
        null => null,
        PyDict mapping => mapping.ToDictionary(p => p.Key, p => Transport(p.Value), StringComparer.Ordinal),
        IReadOnlyDictionary<string, object?> mapping => mapping.ToDictionary(p => p.Key, p => Transport(p.Value), StringComparer.Ordinal),
        IDictionary mapping => mapping.Keys.Cast<string>().ToDictionary(key => key, key => Transport(mapping[key]), StringComparer.Ordinal),
        PyNumber number => TrailValues.Of(number),
        BigInteger number when number >= long.MinValue && number <= long.MaxValue => (long)number,
        PyDateTime instant => instant.IsoFormat(),
        string or PyDecimal => value,
        IEnumerable sequence => sequence.Cast<object?>().Select(Transport).ToArray(),
        _ => value,
    };

    internal static Dictionary<string, object?> Map(params (string Key, object? Value)[] values) =>
        values.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);

    internal static Dictionary<string, object?> Copy(IReadOnlyDictionary<string, object?> source) => new(source, StringComparer.Ordinal);

    internal static IReadOnlyDictionary<string, object?>? Mapping(object? value) =>
        value as IReadOnlyDictionary<string, object?>;

    internal static IReadOnlyDictionary<string, object?>? Child(IReadOnlyDictionary<string, object?> source, string key) =>
        Mapping(source.GetValueOrDefault(key));

    internal static List<IReadOnlyDictionary<string, object?>> Rows(IReadOnlyDictionary<string, object?> source, string key) =>
        source.GetValueOrDefault(key) is IEnumerable rows ? rows.Cast<IReadOnlyDictionary<string, object?>>().ToList() : [];

    /// <summary>Converts stored numeric columns and canonical engine scalars without converting money to JSON numbers.</summary>
    public static double Number(object? value) => value switch
    {
        null => 0,
        PyNumber number => number.IsInt ? number.IntValue : number.FloatValue,
        PyDecimal number => double.Parse(number.ToString(), CultureInfo.InvariantCulture),
        BigInteger number => (double)number,
        _ => Convert.ToDouble(value, CultureInfo.InvariantCulture),
    };

    /// <summary>Uses the certified float renderer for textual source cells and raw statutory scalar renderings.</summary>
    public static string PythonString(object? value) => value switch
    {
        null => "None",
        bool boolean => boolean ? "True" : "False",
        PyNumber number => PythonString(TrailValues.Of(number)),
        double number => PyFloat.Repr(number),
        _ => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "",
    };

    internal static int Count(object? value) => value is null ? 0 : Convert.ToInt32(value, CultureInfo.InvariantCulture);

    internal static bool Bool(object? value) => value is not null && Convert.ToBoolean(value, CultureInfo.InvariantCulture);

    internal static string Text(object? value) => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";

    internal static PyDict Engine(IReadOnlyDictionary<string, object?> row) =>
        row.Aggregate(new PyDict(), (tree, item) => tree.Set(item.Key, item.Value));

    internal static string Iso(DateOnly day) => day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    internal static Dictionary<string, object?> Envelope(IReadOnlyDictionary<string, object?>? run,
        IReadOnlyDictionary<string, object?>? inFlight, bool hasRows = true)
    {
        var calculated = run is not null && hasRows;
        Dictionary<string, object?>? provenance = null;
        if (run is not null)
        {
            provenance = new(StringComparer.Ordinal);
            foreach (var key in new[] { "run_id", "calculation_id", "code_commit", "rule_pack_version",
                "step1_assumption_set_id", "onezero_assumption_set_id", "triggered_by", "tax_year", "program_code" })
            {
                provenance[key] = run[key];
            }
            provenance["produced_at"] = run["run_completed_at"];
            provenance["started_at"] = run["run_started_at"];
        }
        return Map(("calculation_state", calculated ? "calculated" : "not_calculated"), ("run", provenance),
            ("newer_run_in_flight", inFlight is not null), ("in_flight", inFlight),
            ("message", calculated ? null : "Not yet calculated. Run the calculation to see figures."));
    }
}
