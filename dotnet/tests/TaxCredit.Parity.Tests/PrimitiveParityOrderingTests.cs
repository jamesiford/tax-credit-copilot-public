using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Gate G1 (continued): dates, ordering, <c>min</c>/<c>max</c> and string semantics.</summary>
[Trait("Category", "heavy")]
public sealed class PrimitiveParityOrderingTests
{
    private const string File = "primitives.jsonl.gz";

    private static double Dbl(JsonElement d) => PyFloat.FromBits(d.GetProperty("b").GetInt64());

    private static string? Eq<T>(string what, T actual, T expected) =>
        EqualityComparer<T>.Default.Equals(actual, expected) ? null : $"{what}: got '{actual}' expected '{expected}'";

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static DateOnly ParseIso(JsonElement e) => DateOnly.ParseExact(e.GetString()!, "yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Try(Func<DateOnly> f)
    {
        try
        {
            return Iso(f());
        }
        catch (PyException e)
        {
            return e.PythonType;
        }
    }

    [Fact]
    public void Monthrange_matches_python() =>
        PrimitiveParityTests.Run("monthrange", v =>
        {
            var (w, d) = PyDate.MonthRange(v.GetProperty("y").GetInt32(), v.GetProperty("m").GetInt32());
            var o = v.GetProperty("o");
            return Eq("firstWeekday", w, o[0].GetInt32()) ?? Eq("days", d, o[1].GetInt32());
        });

    [Fact]
    public void Month_end_table_matches_python_for_1900_to_2100() =>
        PrimitiveParityTests.Run("month_ends", v =>
        {
            var y = v.GetProperty("y").GetInt32();
            var o = v.GetProperty("o");
            for (var m = 1; m <= 12; m++)
            {
                var (w, d) = PyDate.MonthRange(y, m);
                var err = Eq($"{y}-{m} weekday", w, o[m - 1][0].GetInt32()) ?? Eq($"{y}-{m} days", d, o[m - 1][1].GetInt32());
                if (err is not null)
                {
                    return err;
                }
            }

            return Eq("isleap", PyDate.IsLeap(y), v.GetProperty("leap").GetBoolean());
        });

    [Fact]
    public void Weekday_ordinal_and_isocalendar_match_python()
    {
        PrimitiveParityTests.Run("isoweekday", v =>
        {
            var d = ParseIso(v.GetProperty("d"));
            var o = v.GetProperty("o");
            return Eq("isoweekday", PyDate.IsoWeekday(d), o[0].GetInt32()) ?? Eq("weekday", PyDate.Weekday(d), o[1].GetInt32()) ??
                   Eq("ordinal", PyDate.ToOrdinal(d), o[2].GetInt32());
        });
        PrimitiveParityTests.Run("isocalendar", v =>
        {
            var d = ParseIso(v.GetProperty("d"));
            var o = v.GetProperty("o");
            var (y, w, wd) = PyDate.IsoCalendar(d);
            return Eq("isoyear", y, o[0].GetInt32()) ?? Eq("isoweek", w, o[1].GetInt32()) ?? Eq("isoday", wd, o[2].GetInt32());
        });
    }

    [Fact]
    public void Date_plus_timedelta_matches_python_including_overflow() =>
        PrimitiveParityTests.Run("date_add", v =>
            Eq("d+n", Try(() => PyDate.AddDays(ParseIso(v.GetProperty("d")), v.GetProperty("n").GetInt32())), v.GetProperty("o").GetString()));

    [Fact]
    public void Date_construction_and_replace_match_python_value_errors() =>
        PrimitiveParityTests.Run("date_make", v =>
        {
            var y = v.GetProperty("y").GetInt32();
            var m = v.GetProperty("m").GetInt32();
            var d = v.GetProperty("d").GetInt32();
            return Eq("date()", Try(() => PyDate.Make(y, m, d)), v.GetProperty("o").GetString()) ??
                   Eq("replace()", Try(() => PyDate.Replace(ParseIso(v.GetProperty("replace_from")), y, m, d)), v.GetProperty("o_replace").GetString());
        });

    [Fact]
    public void Date_difference_and_comparison_match_python() =>
        PrimitiveParityTests.Run("date_diff", v =>
        {
            var a = ParseIso(v.GetProperty("a"));
            var b = ParseIso(v.GetProperty("b"));
            var o = v.GetProperty("o");
            return Eq("days", b.DayNumber - a.DayNumber, o[0].GetInt32()) ?? Eq("a<b", a < b, o[1].GetBoolean()) ?? Eq("a==b", a == b, o[2].GetBoolean());
        });

    [Fact]
    public void Date_fromisoformat_matches_python() =>
        PrimitiveParityTests.Run("date_parse", v =>
            Eq("fromisoformat", Try(() => PyDate.FromIsoFormat(v.GetProperty("t").GetString()!)), v.GetProperty("o").GetString()));

    private static Comparer<int> KeyComparer(JsonElement keys, string kind, out Func<int, object> key)
    {
        var list = keys.EnumerateArray().ToList();
        switch (kind)
        {
            case "str":
                var strings = list.Select(e => e.GetString()!).ToList();
                key = i => strings[i];
                return Comparer<int>.Create((a, b) => PyStr.Compare(strings[a], strings[b]));
            case "tuple":
                var tuples = list.Select(e => (First: e[0].GetInt32(), Second: e[1].GetString()!)).ToList();
                key = i => tuples[i];
                return Comparer<int>.Create((a, b) =>
                {
                    var c = tuples[a].First.CompareTo(tuples[b].First);
                    return c != 0 ? c : PyStr.Compare(tuples[a].Second, tuples[b].Second);
                });
            default:
                var nums = list.Select(e => e.ValueKind == JsonValueKind.Object ? Dbl(e) : e.GetInt64()).ToList();
                key = i => nums[i];
                return Comparer<int>.Create((a, b) => PySort.FloatComparer.Compare(nums[a], nums[b]));
        }
    }

    [Fact]
    public void Sorted_is_stable_and_reverse_preserves_input_order_of_ties() =>
        PrimitiveParityTests.Run("sort", v =>
        {
            var keys = v.GetProperty("keys");
            var cmp = KeyComparer(keys, v.GetProperty("kind").GetString()!, out _);
            var indices = Enumerable.Range(0, keys.GetArrayLength()).ToList();
            var actual = PySort.Sorted(indices, i => i, cmp, v.GetProperty("reverse").GetBoolean());
            var expected = v.GetProperty("o").EnumerateArray().Select(e => e.GetInt32()).ToList();
            return actual.SequenceEqual(expected) ? null : $"order [{string.Join(',', actual)}] expected [{string.Join(',', expected)}]";
        });

    [Fact]
    public void Min_and_max_with_key_return_the_first_of_equal_elements() =>
        PrimitiveParityTests.Run("minmax", v =>
        {
            var keys = v.GetProperty("keys");
            var cmp = KeyComparer(keys, v.GetProperty("kind").GetString()!, out _);
            var indices = Enumerable.Range(0, keys.GetArrayLength()).ToList();
            return Eq("min", PySort.MinBy(indices, i => i, cmp), v.GetProperty("min").GetInt32()) ??
                   Eq("max", PySort.MaxBy(indices, i => i, cmp), v.GetProperty("max").GetInt32());
        });

    [Fact]
    public void Float_min_and_max_handle_signed_zero_and_nan_like_python() =>
        PrimitiveParityTests.Run("minmax_float", v =>
        {
            var xs = v.GetProperty("xs").EnumerateArray().Select(Dbl).ToList();
            static string? Same(string what, double actual, JsonElement e) =>
                PyFloat.SameBits(actual, Dbl(e)) ? null : $"{what}: got {PyFloat.Repr(actual)} expected {e.GetProperty("r").GetString()}";
            return Same("min", PyArith.Min(xs), v.GetProperty("min")) ?? Same("max", PyArith.Max(xs), v.GetProperty("max")) ??
                   Same("min2", PyArith.Min(xs[0], xs[^1]), v.GetProperty("min2")) ?? Same("max2", PyArith.Max(xs[0], xs[^1]), v.GetProperty("max2"));
        });

    [Fact]
    public void Upper_strip_and_isspace_match_python() =>
        PrimitiveParityTests.Run("str", v =>
        {
            var s = v.GetProperty("s").GetString()!;
            return Eq("upper", PyStr.Upper(s), v.GetProperty("upper").GetString()) ?? Eq("strip", PyStr.Strip(s), v.GetProperty("strip").GetString()) ??
                   Eq("isspace", PyStr.IsSpace(s), v.GetProperty("isspace").GetBoolean());
        });

    [Fact]
    public void String_comparison_is_by_code_point_like_python() =>
        PrimitiveParityTests.Run("strcmp", v =>
        {
            var a = v.GetProperty("a").GetString()!;
            var b = v.GetProperty("b").GetString()!;
            var c = PyStr.Compare(a, b);
            return Eq("cmp", c, v.GetProperty("cmp").GetInt32()) ?? Eq("lt", c < 0, v.GetProperty("lt").GetBoolean()) ??
                   Eq("eq", c == 0, v.GetProperty("eq").GetBoolean());
        });

    [Fact]
    public void Ordinal_comparison_in_the_BCL_is_not_python_order_so_the_trap_is_real() =>
        // U+10000 (surrogate pair D800 DC00) sorts after U+FFFF in Python but before it for UTF-16 code units.
        Assert.True(string.CompareOrdinal("\U00010000", "\uffff") < 0 && PyStr.Compare("\U00010000", "\uffff") > 0);

    [Fact]
    public void Case_mapping_table_agrees_with_python_for_every_code_point()
    {
        var expected = new Dictionary<int, string>();
        foreach (var v in GoldenFiles.Read(File, "case_table"))
        {
            foreach (var row in v.GetProperty("table").EnumerateArray())
            {
                expected[row[0].GetInt32()] = string.Concat(row[1].EnumerateArray().Select(e => char.ConvertFromUtf32(e.GetInt32())));
            }
        }

        Assert.True(expected.Count > 1000);
        var bad = new List<int>();
        for (var cp = 0; cp < 0x110000; cp++)
        {
            if (cp is >= 0xD800 and <= 0xDFFF)
            {
                continue;
            }

            var s = char.ConvertFromUtf32(cp);
            var want = expected.TryGetValue(cp, out var e) ? e : s;
            if (PyStr.Upper(s) != want)
            {
                bad.Add(cp);
            }
        }

        Assert.True(bad.Count == 0, $"{bad.Count} code points differ, first: {string.Join(',', bad.Take(10).Select(c => c.ToString("x", CultureInfo.InvariantCulture)))}");
    }

    [Fact]
    public void Whitespace_table_agrees_with_python_for_every_code_point()
    {
        var expected = new HashSet<int>();
        foreach (var v in GoldenFiles.Read(File, "space_table"))
        {
            foreach (var cp in v.GetProperty("cps").EnumerateArray())
            {
                expected.Add(cp.GetInt32());
            }
        }

        Assert.True(expected.Count > 20);
        var bad = Enumerable.Range(0, 0x110000).Where(cp => cp is not (>= 0xD800 and <= 0xDFFF) && PyStr.IsSpaceCodePoint(cp) != expected.Contains(cp)).ToList();
        Assert.Empty(bad);
    }

    [Fact]
    public void Unicode_table_version_matches_the_oracle()
    {
        foreach (var v in GoldenFiles.Read(File, "unicode_version"))
        {
            Assert.Equal(PyUnicodeTables.UnicodeVersion, v.GetProperty("v").GetString());
        }
    }
}
