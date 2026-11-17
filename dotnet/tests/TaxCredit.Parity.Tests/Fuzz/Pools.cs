using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Value pools shared by the family generators: tagged scalars, numbers around a threshold on both sides, special floats, and dates that hit month ends and leap days.</summary>
internal static class Pools
{
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private static readonly double[] SpecialDoubles =
        [double.NaN, double.PositiveInfinity, double.NegativeInfinity, 0.0, -0.0, 5e-324, 1e-320, 1e-9, 1e300, -1e300, 1.7976931348623157e308, -1.7976931348623157e308, 1e22, 1e23, 1e15, 1e16];

    public static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", Inv);

    /// <summary>Adds days, staying put when the result would leave the representable range.</summary>
    public static DateOnly Shift(DateOnly d, int days) => d.DayNumber + days is >= 0 and <= 3652058 ? d.AddDays(days) : d;

    public static PyDict Date(DateOnly d) => new PyDict().Add("$date", Iso(d));

    public static PyDict Dec(string text) => new PyDict().Add("$dec", text);

    public static PyDict Dt(string iso) => new PyDict().Add("$dt", iso);

    /// <summary>A number within a few ulps, half-cents or units of <paramref name="t"/>: an int when <paramref name="t"/> is integral and a coin says so, else a float.</summary>
    public static object Around(Rng r, double t)
    {
        double v = r.Int(0, 13) switch
        {
            0 or 1 => t,
            2 => Math.BitIncrement(t),
            3 => Math.BitDecrement(t),
            4 => t + 0.005,
            5 => t - 0.005,
            6 => t + 0.004999999999,
            7 => t + 1,
            8 => t - 1,
            9 => t + r.Uniform(-3, 3),
            10 => Math.Round(t + r.Uniform(-2, 2), r.Int(0, 3)),
            11 => t * (1 + 1e-12),
            12 => t * (1 - 1e-12),
            _ => t + (r.Int(-4, 4) * 0.01),
        };
        return v == Math.Floor(v) && Math.Abs(v) < 1e15 && r.Chance(0.3) ? (object)(long)v : v;
    }

    /// <summary>A float or int that is not an ordinary quantity: NaN, infinities, subnormals, the largest double, huge ints beyond 64 bits.</summary>
    public static object Special(Rng r) => r.Int(0, 9) switch
    {
        0 => BigInteger.Pow(10, 25),
        1 => -BigInteger.Pow(10, 30),
        2 => long.MaxValue,
        3 => (long)Math.Pow(2, 53) + 1,
        _ => SpecialFloat(r),
    };

    /// <summary>A float or an int that is not an ordinary quantity, never beyond 64 bits (for ports typed over <c>PyNumber</c>).</summary>
    public static object SpecialNumber(Rng r) => r.Int(0, 5) switch
    {
        0 => long.MaxValue,
        1 => (long)Math.Pow(2, 53) + 1,
        _ => SpecialFloat(r),
    };

    /// <summary>A float that is not an ordinary quantity (for functions whose port signature takes doubles).</summary>
    public static double SpecialFloat(Rng r) => r.Pick(SpecialDoubles);

    /// <summary>A value of a type the function does not expect: strings (numeric and not), bools, lists, <c>null</c>.</summary>
    public static object? Weird(Rng r) => r.Int(0, 11) switch
    {
        0 => null,
        1 => true,
        2 => false,
        3 => "35.5",
        4 => "abc",
        5 => " 12 ",
        6 => string.Empty,
        7 => "inf",
        8 => new List<object?>(),
        9 => new List<object?> { 1L },
        10 => new PyDict(),
        _ => "1_0",
    };

    /// <summary>A number that is usually ordinary and sometimes special or mistyped (<paramref name="oddity"/> is the combined probability).</summary>
    public static object? Mostly(Rng r, Func<object?> ordinary, double oddity = 0.04)
    {
        if (!r.Chance(oddity))
        {
            return ordinary();
        }

        return r.Chance(0.6) ? Special(r) : Weird(r);
    }

    /// <summary>A date on a boundary more often than by chance: month ends, leap days, year ends, the day after.</summary>
    public static DateOnly Day(Rng r, int fromYear, int toYear)
    {
        var year = r.Int(fromYear, toYear);
        var month = r.Int(1, 12);
        var last = DateTime.DaysInMonth(year, month);
        var day = r.Int(0, 5) switch
        {
            0 => last,
            1 => 1,
            2 => Math.Max(1, last - 1),
            3 => month == 2 ? 28 : 15,
            _ => r.Int(1, last),
        };
        if (r.Chance(0.06))
        {
            var y = r.Pick(new[] { 2020, 2024, 2023, 2028 });
            return new DateOnly(y, 2, DateTime.DaysInMonth(y, 2)).AddDays(r.Int(-1, 1));
        }

        return new DateOnly(year, month, day);
    }

    /// <summary>A short run of employee identifiers: plain, numeric, unicode, and ties.</summary>
    public static object? EmployeeId(Rng r, int i) => r.Int(0, 11) switch
    {
        0 => (long)i,
        1 => null,
        2 => "10",
        3 => "9",
        4 => "\u00e9",
        5 => "\U0001F600",
        6 => $"E{i % 7}",
        7 => string.Empty,
        _ => $"E{i}",
    };

    /// <summary>Seconds-free ISO timestamps for the <c>$dt</c> tag, with and without microseconds and offsets.</summary>
    public static PyDict DateTimeTag(Rng r)
    {
        var d = Day(r, 2019, 2026);
        var time = r.Pick(new[] { "09:30:15", "00:00:00", "23:59:59", "12:00:00.123456", "09:30:15.500000", "23:59:59.999999", "09:30:15+00:00", "09:30:00+05:30" });
        return Dt($"{Iso(d)}T{time}");
    }
}
