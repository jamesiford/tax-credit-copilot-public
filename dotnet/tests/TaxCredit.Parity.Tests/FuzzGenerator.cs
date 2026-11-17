using System.Globalization;
using System.Text;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>SplitMix64: a tiny deterministic generator whose stream is fixed by the algorithm, not by the .NET version.</summary>
internal sealed class Rng(ulong seed)
{
    private ulong _state = seed;

    public ulong NextU64()
    {
        _state += 0x9E3779B97F4A7C15UL;
        var z = _state;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
        return z ^ (z >> 31);
    }

    /// <summary>Uniform integer in [lo, hi].</summary>
    public int Int(int lo, int hi) => lo + (int)(NextU64() % (ulong)(hi - lo + 1));

    /// <summary>Uniform double in [0, 1).</summary>
    public double Unit() => (NextU64() >> 11) * (1.0 / (1UL << 53));

    public double Uniform(double lo, double hi) => lo + ((hi - lo) * Unit());

    public bool Chance(double p) => Unit() < p;

    public T Pick<T>(IReadOnlyList<T> items) => items[Int(0, items.Count - 1)];
}

/// <summary>A scenario row: only present keys are serialised, so absent stays absent.</summary>
internal sealed class FuzzRow
{
    public Dictionary<string, object?> Cells { get; } = new(StringComparer.Ordinal);

    public FuzzRow Clone()
    {
        var r = new FuzzRow();
        foreach (var kv in Cells)
        {
            r.Cells[kv.Key] = kv.Value;
        }

        return r;
    }
}

/// <summary>A generated request: rows plus the operation parameters as ready-made JSON.</summary>
internal sealed class FuzzScenario(string id, string op, List<FuzzRow> rows, string paramsJson)
{
    public string Id { get; } = id;

    public string Op { get; } = op;

    public List<FuzzRow> Rows { get; } = rows;

    public string ParamsJson { get; } = paramsJson;

    public string ToJson() => ToJson(Rows);

    public string ToJson(IReadOnlyList<FuzzRow> rows)
    {
        var sb = new StringBuilder();
        sb.Append("{\"id\":").Append(J.Str(Id)).Append(",\"op\":").Append(J.Str(Op)).Append(",\"rows\":[");
        for (var i = 0; i < rows.Count; i++)
        {
            if (i > 0)
            {
                sb.Append(',');
            }

            sb.Append('{');
            var first = true;
            foreach (var key in new[] { "Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State" })
            {
                if (!rows[i].Cells.TryGetValue(key, out var v))
                {
                    continue;
                }

                if (!first)
                {
                    sb.Append(',');
                }

                first = false;
                sb.Append(J.Str(key)).Append(':').Append(J.Value(v));
            }

            sb.Append('}');
        }

        return sb.Append("],\"params\":").Append(ParamsJson).Append('}').ToString();
    }
}

/// <summary>Minimal JSON writing with Python-compatible numbers and ASCII-only strings.</summary>
internal static class J
{
    public static string Str(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (var c in s)
        {
            switch (c)
            {
                case '"':
                    sb.Append("\\\"");
                    break;
                case '\\':
                    sb.Append("\\\\");
                    break;
                default:
                    if (c is >= ' ' and <= '~')
                    {
                        sb.Append(c);
                    }
                    else
                    {
                        sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }

                    break;
            }
        }

        return sb.Append('"').ToString();
    }

    public static string Value(object? v) => v switch
    {
        null => "null",
        string s => Str(s),
        long l => l.ToString(CultureInfo.InvariantCulture),
        int i => i.ToString(CultureInfo.InvariantCulture),
        double d => PyFloat.Repr(d),
        bool b => b ? "true" : "false",
        _ => throw new InvalidOperationException(v.GetType().Name),
    };

    public static string Num(PyNumber n) => n.IsInt ? n.IntValue.ToString(CultureInfo.InvariantCulture) : PyFloat.Repr(n.FloatValue);
}

/// <summary>Seeded scenario generator, written independently of the Python one (so the two streams can disagree only through the engines).</summary>
internal static class FuzzGenerator
{
    private static readonly string[] Units = ["GA_A", "GA_B", "TN_C", "SC_D", "GA_\u00e9", "GA_Z9", "NC_X", "GA_\U00010000"];
    private static readonly string[] Codes = ["Regular", "Regular", "Regular", "Overtime", "Bonus", "Mileage", "Commission", "Relocation"];
    private static readonly string[] MeasuringDates = ["last_day", "last_day", "last_day", "15", "1", "31", "28", "0", "-3", "abc", "", " 20 ", "1_5", "\u0661\u0665", "99"];
    private static readonly double[] AvgHours = [0.0, 8.0, 20.0, 31.9, 32.0, 34.0, 34.99, 34.995, 35.0, 35.005, 40.0, 44.5, 60.25];
    private static readonly double[] AvgWages = [0.0, 150.0, 635.99, 636.0, 679.995, 680.0, 686.0, 700.0, 1000.0, 2500.5];

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static (DateOnly Start, DateOnly End)[] Periods(Rng r, DateOnly start, int n, string kind)
    {
        var list = new List<(DateOnly, DateOnly)>();
        var cur = start;
        for (var i = 0; i < n; i++)
        {
            var k = kind == "mixed" ? r.Pick(new[] { "weekly", "biweekly", "semimonthly", "monthly", "short", "long" }) : kind;
            DateOnly end;
            switch (k)
            {
                case "weekly":
                    end = cur.AddDays(6);
                    break;
                case "biweekly":
                    end = cur.AddDays(13);
                    break;
                case "semimonthly":
                    end = cur.Day <= 15 ? new DateOnly(cur.Year, cur.Month, 15) : new DateOnly(cur.Year, cur.Month, 1).AddMonths(1).AddDays(-1);
                    if (end < cur)
                    {
                        end = cur.AddDays(14);
                    }

                    break;
                case "monthly":
                    end = new DateOnly(cur.Year, cur.Month, 1).AddMonths(1).AddDays(-1);
                    break;
                case "short":
                    end = cur.AddDays(r.Int(0, 3));
                    break;
                default:
                    end = cur.AddDays(r.Int(30, 40));
                    break;
            }

            list.Add((cur, end));
            cur = end.AddDays(1);
        }

        return [.. list];
    }

    private static FuzzRow Row(string ee, string unit, DateOnly pps, DateOnly ppe, DateOnly pay, object? hours, object? wages, string? code, string? fein)
    {
        var row = new FuzzRow();
        row.Cells["Employee_ID"] = ee;
        row.Cells["Worksite_ID"] = unit;
        row.Cells["Entity_FEIN"] = fein;
        row.Cells["Pay_Period_Start"] = Iso(pps);
        row.Cells["Pay_Period_End"] = Iso(ppe);
        row.Cells["Pay_Date"] = Iso(pay);
        row.Cells["Hours_Worked"] = hours;
        row.Cells["Gross_Wages"] = wages;
        row.Cells["Pay_Code"] = code;
        return row;
    }

    public static List<FuzzRow> Dataset(Rng r)
    {
        var rows = new List<FuzzRow>();
        var kind = r.Pick(new[] { "weekly", "biweekly", "semimonthly", "monthly", "mixed" });
        var start = new DateOnly(2023, 1, 1).AddDays(r.Int(0, 540));
        var nEmp = r.Int(1, 9);
        var pool = Units.OrderBy(_ => r.NextU64()).Take(r.Int(1, 3)).ToArray();
        for (var e = 0; e < nEmp; e++)
        {
            var ee = r.Pick(new[] { $"E{e:000}", $"E{e}", $"x{e}", $"\u00c9{e}" });
            var first = start.AddDays(r.Int(0, 120));
            var avgH = r.Pick(AvgHours);
            var avgW = r.Pick(AvgWages);
            var unit = r.Pick(pool);
            foreach (var (pps, ppe) in Periods(r, first, r.Int(1, 60), kind))
            {
                if (r.Chance(0.08))
                {
                    unit = r.Pick(pool);
                }

                var weeks = (ppe.DayNumber - pps.DayNumber + 1) / 7.0;
                object? h = PyRound.Round(Math.Max(0.0, (avgH * weeks) + r.Uniform(-1.5, 1.5)), r.Pick(new[] { 2, 2, 2, 3 }));
                object? w = PyRound.Round(Math.Max(0.0, (avgW * weeks) + r.Uniform(-30, 30)), 2);
                if (r.Chance(0.03))
                {
                    h = null;
                    w = string.Empty;
                }

                if (r.Chance(0.04) && h is double hd)
                {
                    h = PyFloat.Repr(hd);
                }

                if (r.Chance(0.02))
                {
                    w = (long)Math.Round((double)(w is double wd ? wd : 0.0));
                }

                var pay = ppe.AddDays(r.Int(0, 9));
                rows.Add(Row(ee, unit, pps, ppe, pay, h, w, r.Pick(Codes), r.Pick(new[] { "58-1", "99-2", string.Empty })));
                if (r.Chance(0.04))
                {
                    rows.Add(Row(ee, unit, pps, ppe, pay, PyRound.Round(r.Uniform(0, 5), 2), PyRound.Round(r.Uniform(0, 100), 2), r.Pick(Codes), "58-1"));
                }
            }
        }

        if (rows.Count > 0 && r.Chance(0.04))
        {
            // Corrupt one row so the error paths (KeyError, ValueError, TypeError, InvalidOperation) are fuzzed too.
            var row = rows[r.Int(0, rows.Count - 1)];
            switch (r.Int(0, 6))
            {
                case 0:
                    row.Cells.Remove("Pay_Date");
                    break;
                case 1:
                    row.Cells["Pay_Date"] = "garbage";
                    break;
                case 2:
                    row.Cells["Hours_Worked"] = "abc";
                    break;
                case 3:
                    row.Cells.Remove("Gross_Wages");
                    break;
                case 4:
                    row.Cells["Worksite_ID"] = null;
                    break;
                case 5:
                    row.Cells["Hours_Worked"] = 1e300;
                    break;
                default:
                    row.Cells["Pay_Period_End"] = row.Cells["Pay_Period_Start"];
                    row.Cells["Pay_Period_Start"] = "2099-01-01";
                    break;
            }
        }

        if (r.Chance(0.3))
        {
            rows = [.. rows.OrderBy(_ => r.NextU64())];
        }

        return rows;
    }

    private static string Pack(Rng r)
    {
        var parts = new List<string>
        {
            "\"min_weekly_hours\":" + J.Num(r.Chance(0.5) ? PyNumber.OfFloat(r.Pick(new[] { 35.0, 32.0, 37.5, 20.0 })) : PyNumber.OfInt(r.Pick(new[] { 35, 32, 30 }))),
            "\"min_weekly_wages\":" + J.Num(r.Chance(0.5) ? PyNumber.OfFloat(r.Pick(new[] { 686.0, 636.0, 0.0, 700.0, 680.5 })) : PyNumber.OfInt(r.Pick(new[] { 686, 0, 700 }))),
            "\"citation\":\"fuzz\"",
            "\"measuring_date\":" + J.Str(r.Pick(MeasuringDates)),
        };
        if (r.Chance(0.3))
        {
            parts.Add("\"pt_band_hours\":" + r.Pick(new[] { "[20.0,32.0]", "[20,32]", "[25.5,34.9]", "[0,35]" }));
            parts.Add("\"pt_weight\":" + r.Pick(new[] { "0.5", "0.5", "0.25", "0.0", "1", "null" }));
        }

        if (r.Chance(0.3))
        {
            parts.Add("\"included_pay_codes\":" + r.Pick(new[] { "[\"Regular\",\"Overtime\",\"Bonus\",\"Commission\"]", "[\"Regular\"]", "[]" }));
        }

        if (r.Chance(0.3))
        {
            parts.Add("\"excluded_pay_codes\":" + r.Pick(new[] { "[\"Mileage\"]", "[\"Bonus\",\"Mileage\"]", "[]" }));
        }

        if (r.Chance(0.5))
        {
            var m = new List<string>();
            void Maybe(string key, string[] values)
            {
                if (r.Chance(0.4))
                {
                    m.Add("\"" + key + "\":" + r.Pick(values));
                }
            }

            Maybe("minimum_pay_period_days", ["0", "1", "3", "7", "10", "14", "15"]);
            Maybe("short_periods_excluded_from_numerator", ["true", "false"]);
            Maybe("pay_period_denominator_mode", ["\"actual_span\"", "\"frequency_code\""]);
            Maybe("min_max_span_mode", ["\"exclusive_days\"", "\"inclusive_days\""]);
            Maybe("count_zero_hour_periods", ["true", "false"]);
            Maybe("average_decimals", ["0", "1", "2", "2", "3", "4"]);
            Maybe("maximum_weeks_without_review", ["5.0", "10", "53.0", "100.0"]);
            Maybe("exclude_off_cycle_periods", ["true", "false"]);
            if (m.Count > 0)
            {
                parts.Add("\"methodology\":{" + string.Join(',', m) + "}");
            }
        }

        return "{" + string.Join(',', parts) + "}";
    }

    public static FuzzScenario Scenario(Rng r, string id)
    {
        var rows = Dataset(r);
        var pack = Pack(r);
        var ty = r.Pick(new[] { 2023, 2024 });
        var kind = r.Pick(new[] { "calendar", "calendar", "march", "window", "stub" });
        var p = new List<string> { $"\"tax_year\":{ty}", "\"pack\":" + pack, "\"with_trail\":" + (r.Chance(0.7) ? "true" : "false") };
        string startMonth;
        switch (kind)
        {
            case "calendar":
                startMonth = $"{ty}-01-01";
                if (r.Chance(0.5))
                {
                    p.Add($"\"fiscal_window\":[\"{ty}-01-01\",\"{ty}-12-31\"]");
                }

                break;
            case "march":
                p.Add("\"fiscal_year_end_month\":3");
                startMonth = $"{ty - 1}-04-01";
                break;
            default:
                var b = new DateOnly(ty - 1, r.Int(1, 12), kind == "stub" ? r.Int(2, 28) : 1);
                p.Add($"\"fiscal_window\":[\"{Iso(b)}\",\"{Iso(b.AddDays(r.Int(340, 380)))}\"]");
                startMonth = Iso(new DateOnly(b.Year, b.Month, 1));
                break;
        }

        var opRoll = r.Unit();
        string op;
        if (opRoll < 0.9)
        {
            op = r.Chance(0.5) ? "pay_period" : "min_max";
            p.Add("\"analysis_start_month\":\"" + startMonth + "\"");
        }
        else if (opRoll < 0.95)
        {
            op = "average_headcount";
            p = [$"\"state\":{J.Str(r.Pick(new[] { "GA", "TN", "SC", "NC", "XX" }))}", $"\"tax_year\":{ty}", "\"pack\":" + pack];
            if (r.Chance(0.5))
            {
                p.Add($"\"window\":[\"{ty}-01-01\",\"{ty}-12-31\"]");
            }
        }
        else
        {
            op = "preprocess";
            p = [$"\"tax_year\":{ty}", "\"with_trail\":true", "\"fiscal_year_end_month\":" + r.Pick(new[] { 12, 3, 6 })];
        }

        return new FuzzScenario(id, op, rows, "{" + string.Join(',', p) + "}");
    }
}
