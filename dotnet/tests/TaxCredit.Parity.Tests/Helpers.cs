using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>The direct-function ops (<c>helper</c>, <c>fiscal</c>) of the request schema.</summary>
internal static class Helpers
{
    private static DateOnly D(JsonElement e) => DateOnly.ParseExact(e.GetString()!, "yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Iso(DateOnly d) => EngineRunner.Iso(d);

    public static object? Run(JsonElement p)
    {
        var name = p.GetProperty("name").GetString();
        var a = p.TryGetProperty("args", out var args) ? args : default;
        switch (name)
        {
            case "fiscal_year_of":
                return OneZeroCalendar.FiscalYearOf(D(a[0]), a[1].GetInt64());
            case "fiscal_window_start":
                return Iso(OneZeroCalendar.FiscalWindowStart(a[0].GetInt64(), a[1].GetInt64()));
            case "twelve_month_ends":
                return OneZeroCalendar.TwelveMonthEnds(D(a[0])).Select(d => (object?)Iso(d)).ToList();
            case "measuring_date_for_month":
                return Iso(OneZeroCalendar.MeasuringDateForMonth(D(a[0]), a[1].ValueKind == JsonValueKind.Null ? null : a[1].GetString()));
            case "adjusted_target":
                return Iso(OneZeroCalendar.AdjustedTargetForMonth(D(a[0]), D(a[1]), a[2].GetBoolean()));
            case "infer_frequency":
                return OneZeroShared.InferFrequency(a[0].GetInt64());
            case "round_half_up":
                return OneZeroEligibility.RoundHalfUp(PyFloat.FromBits(BitConverter.DoubleToInt64Bits(Number(a[0]))), a[1].GetInt32());
            case "classify_eligibility":
                var (w, ph, pw) = OneZeroEligibility.Classify(Number(a[0].GetProperty("avg_weekly_hours")), Number(a[0].GetProperty("avg_weekly_wages")), EngineRunner.Pack(p.GetProperty("pack")));
                return new List<object?> { w, ph, pw };
            case "qualifies":
                var row = EngineRunner.Row(a[0]);
                return OneZeroShared.Qualifies(row, EngineRunner.Methodology(p.GetProperty("methodology")));
            default:
                throw new PyUnsupportedException("Unknown helper " + name);
        }
    }

    private static double Number(JsonElement e) => double.Parse(e.GetRawText(), NumberStyles.Float, CultureInfo.InvariantCulture);

    public static object? Fiscal(JsonElement p)
    {
        var name = p.GetProperty("name").GetString();
        var a = p.GetProperty("args");
        switch (name)
        {
            case "resolve_tax_year":
                return FiscalWindow.ResolveTaxYear(D(a[0]), D(a[1]), a[2].GetString()!);
            case "window_from_client_rules":
                return FiscalWindow.FromClientRules(D(a[0]), D(a[1]), a[2].GetString()!, a.GetArrayLength() > 3 ? a[3].GetString()! : string.Empty).AsDict();
            case "assumed_calendar_window":
                var w = FiscalWindow.AssumedCalendar(a[0].GetInt64(), a[1].GetString()!);
                return CloneWith(w.AsDict(), w);
            default:
                throw new PyUnsupportedException("Unknown fiscal op " + name);
        }
    }

    private static PyDict CloneWith(PyDict d, FiscalWindow w)
    {
        var result = new PyDict();
        foreach (var kv in d)
        {
            result.Add(kv.Key, kv.Value);
        }

        return result.Add("_assumed", w.Assumed).Add("_is_calendar", w.IsCalendar).Add("_matters", w.ConventionMatters);
    }
}
