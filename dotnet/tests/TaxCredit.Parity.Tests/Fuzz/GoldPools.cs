using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Input pools for the gold-projection fuzz: what <c>_dec</c>, <c>_day</c> and <c>_flag</c> are asked to coerce, with ties, magnitudes, specials and non-numbers.</summary>
internal static class GoldPools
{
    private static readonly BigInteger Ten = 10;

    private static readonly object?[] DecFixed =
    [
        null, string.Empty, 0L, 1L, -1L, 7L, 0.0, -0.0, 1.5, 0.1 + 0.2, 2.675, 1.005, 0.285, 1.115, 8.345, 8.355, 0.125, 0.375, 0.625, -0.125, 5e-324, 1e-7, 1e-5, 1e-4, 0.00005,
        0.00015, 0.00025, 1e15, 1e16, 1e22, 1e23, 1e27, 1e28, 1.7976931348623157e308, -1e27, 123456789012345678.9,
        "1972.36", "68.58", "0.005", "0.015", "0.025", "0.035", "-0.005", "-0.015", "0.00005", "0.00015", "0.00025", "0.0001", "1E+2", "1e-3", "-0.001", "  7.255 ", "1_000.125",
        "+5", ".5", "5.", "-.5e1", "0x10", "abc", "1,5", "1.2.3", "--1", " ", "NaN", "nan", "-nan", "+NaN", "nan12", "sNaN", "inf", "-inf", "Infinity", "-Infinity", "1e5", "1E-30", "0E+5",
        "-0", "-0.0", "-0.00", "9999999999999999999999999.99", "99999999999999999999999999.99", "999999999999999999999999999.99", "9999999999999999999999999999", "99999999999999999999999999999",
        "0.00000000000000000000000000001", "123456789.123456789123456789", true, false,
        BigInteger.Pow(Ten, 18), BigInteger.Pow(Ten, 26), BigInteger.Pow(Ten, 27), BigInteger.Pow(Ten, 28), BigInteger.Pow(Ten, 30), -BigInteger.Pow(Ten, 27), BigInteger.Pow(2, 64),
        double.NaN, double.PositiveInfinity, double.NegativeInfinity,
    ];

    private static readonly string[] DecTags =
    [
        "0.005", "0.015", "-0.005", "1E+2", "1E+25", "1E+26", "1E+27", "-0.00", "0E+5", "0E-30", "1E-30", "100.000", "1.23456789012345678901234567890",
        "12345678901234567890123456.785", "12345678901234567890123456.795", "99999999999999999999999999.995", "NaN", "-NaN", "NaN12", "sNaN", "Infinity", "-Infinity", "2.50", "0", "0.00",
    ];

    private static readonly object?[] DayFixed =
    [
        null, string.Empty, "2023-01-01", "2023-01-01T10:00:00", "2023-01-01 10:00:00", "2023-01-01Z", "2023-01-01garbage", "2024-02-29", "2023-02-29", "2023-02-28", "2023-13-01", "2023-00-10",
        "2023-04-31", "2023-12-32", "0001-01-01", "0000-01-01", "9999-12-31", "20230101", "2023W011", "2023-W01-1", "2023-W53-1", "2020-W53-7", "2023-W01", "2023-01", "2023", "23-01-01",
        "2023/01/01", "01/02/2023", " 2023-01-01", "2023-1-1", "2023-01-1", "abcdefghij", "None", "N", " ", "\t", 20230101L, 2023L, 0L, -1L, 1.5, 20230101.0, true, false,
        double.NaN, double.PositiveInfinity, "2019-12-30", "2021-01-03", "2000-02-29", "1900-02-29", "2100-02-29", "2023-11-31",
    ];

    private static readonly object?[] FlagFixed =
    [
        null, true, false, 0L, 1L, -1L, 2L, 0.0, -0.0, 0.5, double.NaN, double.PositiveInfinity, string.Empty, "0", "False", " ", "x", BigInteger.Pow(Ten, 30),
    ];

    private static readonly string[] TextPool = ["x", "GA_1", "Cook", "Regular", "58-1234567", "3", "\u00e9", "a\0b", "None", "  ", string.Empty];

    /// <summary>A value for a decimal column: ordinary money most of the time, an edge or mistyped one otherwise.</summary>
    public static object? Dec(Rng r) => r.Int(0, 9) switch
    {
        < 3 => Money(r),
        < 6 => r.Pick(DecFixed),
        7 => Pools.Dec(r.Pick(DecTags)),
        _ => Random(r),
    };

    /// <summary>A plausible amount: a rounded float, a text amount, or an int.</summary>
    public static object Money(Rng r) => r.Int(0, 3) switch
    {
        0 => Math.Round(r.Uniform(0, 6000), r.Int(0, 4)),
        1 => Math.Round(r.Uniform(0, 6000), 2).ToString("F2", System.Globalization.CultureInfo.InvariantCulture),
        2 => (long)r.Int(0, 6000),
        _ => Math.Round(r.Uniform(0, 90), r.Int(0, 3)),
    };

    private static object Random(Rng r)
    {
        var x = r.Uniform(-1, 1) * Math.Pow(10.0, r.Int(-8, 12));
        return r.Int(0, 4) switch
        {
            0 => x,
            1 => Math.Round(x, r.Int(0, 5)),
            2 => x.ToString("F" + r.Int(0, 6), System.Globalization.CultureInfo.InvariantCulture),
            3 => (r.Int(-10000000, 10000000) / 1000.0).ToString("F3", System.Globalization.CultureInfo.InvariantCulture),
            _ => (long)r.Int(-1000000, 1000000),
        };
    }

    /// <summary>A value for a date column: ISO text, tagged dates and datetimes, and every shape <c>date.fromisoformat</c> accepts or refuses.</summary>
    public static object? Day(Rng r) => r.Int(0, 9) switch
    {
        < 3 => Pools.Iso(Pools.Day(r, 2019, 2026)),
        3 => Pools.Date(Pools.Day(r, 1990, 2030)),
        4 => Pools.DateTimeTag(r),
        5 => Pools.Iso(Pools.Day(r, 2019, 2026)).Replace("-", string.Empty, StringComparison.Ordinal),
        6 => Pools.Iso(Pools.Day(r, 2019, 2026)) + "T00:00:00",
        _ => r.Pick(DayFixed),
    };

    /// <summary>A value for a boolean column.</summary>
    public static object? Flag(Rng r) => r.Int(0, 9) switch
    {
        < 4 => r.Chance(0.5),
        4 => Pools.Dec(r.Pick(new[] { "0", "0.00", "-0.00", "NaN", "0.01" })),
        5 => new List<object?> { r.Pick(new object[] { 0L, 1L }) },
        6 => new PyDict().Add("a", 1L),
        7 => Pools.Date(Pools.Day(r, 2023, 2023)),
        _ => r.Pick(FlagFixed),
    };

    /// <summary>A text column value (identifiers, FEINs, job titles, pay codes) including unicode, NUL and non-strings.</summary>
    public static object? Text(Rng r) => r.Int(0, 9) switch
    {
        < 6 => r.Pick(TextPool),
        6 => null,
        7 => r.Pick(new object[] { 0L, 5L, 5.5, 0.0, false, true, double.NaN }),
        8 => Pools.Dec("2.50"),
        _ => r.Pick(new[] { "\u4e2d\u6587", "\U00010000x", "e\u0301", "\ud800", "a\udfffb", new string('x', 200), "'q'", "\"dq\"" }),
    };

    /// <summary>An employee identifier string, unicode and lone surrogates included.</summary>
    public static string EmployeeId(Rng r) => r.Pick(new[] { "E1", string.Empty, "0", "48685377", "E 1", "\u00c91", "e\u0301", "\u4e2d\u6587", "a\0b", "\U00010000x", new string('x', 60), "\n", "'quote'", "None", "NaN", "\ud800", "a\udfffb", "E001", "\u0130stanbul" });
}
