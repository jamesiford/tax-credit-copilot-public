using System.Numerics;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// <c>OneZeroMethodology.from_pack_json</c>: builds the methodology from a rule pack's optional <c>methodology</c> block. Absent or partial blocks
/// inherit the certified defaults; unknown keys raise rather than being dropped, because a typo would otherwise leave a pack silently running
/// certified defaults while its author believed it was overridden.
/// </summary>
public static class OneZeroMethodologyJson
{
    // `sorted(f.name for f in fields(cls))`, which is what the error message prints.
    private static readonly string[] Known =
    [
        "average_decimals", "count_zero_hour_periods", "exclude_off_cycle_periods", "maximum_weeks_without_review",
        "min_max_span_mode", "minimum_pay_period_days", "pay_period_denominator_mode", "short_periods_excluded_from_numerator",
    ];

    /// <summary>Builds the methodology from a <c>methodology</c> block.</summary>
    /// <param name="block">The block: <c>null</c> or an empty mapping means the certified defaults.</param>
    /// <returns>The methodology.</returns>
    /// <exception cref="PyValueError">For an unknown key or an invalid value.</exception>
    /// <exception cref="PyUnsupportedException">For a value Python would store with a type this record cannot hold (a float where an int is declared).</exception>
    public static OneZeroMethodology FromPackJson(object? block)
    {
        if (!Truthy(block))
        {
            return new OneZeroMethodology();
        }

        var d = block as PyDict ?? throw new PyUnsupportedException("a methodology block that is not an object is not modelled");
        var unknown = PySort.Sorted(d.Keys.Where(k => !Known.Contains(k, StringComparer.Ordinal)), k => k, PyStr.Comparer);
        if (unknown.Count > 0)
        {
            throw new PyValueError($"unknown one_zero.methodology key(s): {string.Join(", ", unknown)}. Valid keys: {string.Join(", ", Known)}");
        }

        var invalid = new List<string>();
        if (!InSet(Get(d, "pay_period_denominator_mode", "actual_span"), "actual_span", "frequency_code"))
        {
            invalid.Add("pay_period_denominator_mode");
        }

        if (!InSet(Get(d, "min_max_span_mode", "exclusive_days"), "exclusive_days", "inclusive_days"))
        {
            invalid.Add("min_max_span_mode");
        }

        if (Sign(ToInt(Get(d, "minimum_pay_period_days", 7L))) < 0)
        {
            invalid.Add("minimum_pay_period_days");
        }

        if (invalid.Count > 0)
        {
            throw new PyValueError($"invalid one_zero.methodology value(s): {string.Join(", ", invalid)}");
        }

        return Build(d);
    }

    private static OneZeroMethodology Build(PyDict d) => new()
    {
        MinimumPayPeriodDays = d.TryGetValue("minimum_pay_period_days", out var days) ? Exactly<long>(days, "minimum_pay_period_days") : 7,
        ShortPeriodsExcludedFromNumerator = d.TryGetValue("short_periods_excluded_from_numerator", out var s) ? Exactly<bool>(s, "short_periods_excluded_from_numerator") : false,
        PayPeriodDenominatorMode = d.TryGetValue("pay_period_denominator_mode", out var p) ? Exactly<string>(p, "pay_period_denominator_mode") : "actual_span",
        MinMaxSpanMode = d.TryGetValue("min_max_span_mode", out var m) ? Exactly<string>(m, "min_max_span_mode") : "exclusive_days",
        CountZeroHourPeriods = !d.TryGetValue("count_zero_hour_periods", out var c) || Exactly<bool>(c, "count_zero_hour_periods"),
        AverageDecimals = d.TryGetValue("average_decimals", out var a) ? checked((int)Exactly<long>(a, "average_decimals")) : 2,
        MaximumWeeksWithoutReview = d.TryGetValue("maximum_weeks_without_review", out var w) ? Weeks(w) : PyNumber.OfFloat(53.0),
        ExcludeOffCyclePeriods = d.TryGetValue("exclude_off_cycle_periods", out var o) && Exactly<bool>(o, "exclude_off_cycle_periods"),
    };

    private static PyNumber Weeks(object? value) => value switch
    {
        long l => PyNumber.OfInt(l),
        double x => PyNumber.OfFloat(x),
        _ => throw new PyUnsupportedException("maximum_weeks_without_review must be an int or a float"),
    };

    // The dataclass stores whatever JSON type it was given (cls(**block) does not coerce); a typed record cannot, so a mistyped value is refused loudly.
    private static T Exactly<T>(object? value, string name) =>
        value is T typed ? typed : throw new PyUnsupportedException($"methodology.{name} is stored uncoerced by Python; a {value?.GetType().Name ?? "null"} is not modelled");

    private static object? Get(PyDict d, string key, object? fallback) => d.TryGetValue(key, out var v) ? v : fallback;

    private static bool InSet(object? value, params string[] allowed) => value is string s && allowed.Contains(s, StringComparer.Ordinal);

    private static bool Truthy(object? v) => ProximityCoerce.Truthy(v);

    private static int Sign(object value) => value is BigInteger b ? b.Sign : Math.Sign((long)value);

    private static object ToInt(object? value) => ProximityCoerce.ToInt(value);
}
