using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>The outcome of one request: either a result tree (plus trail) or the name of the Python exception it mirrors.</summary>
/// <param name="Ok">True for a result.</param>
/// <param name="Result">The result tree.</param>
/// <param name="Trail">The trail tree, when recorded.</param>
/// <param name="Error">The Python exception type name, or a <c>CSHARP:</c>/<c>UNSUPPORTED:</c> marker for a port bug or gap.</param>
internal sealed record EngineOutcome(bool Ok, object? Result, object? Trail, string? Error)
{
    public string? FloatDigest => Ok ? JsonTree.FloatDigest(new List<object?> { Result, Trail }) : null;
}

/// <summary>Decodes schema requests (see <c>parity/engine_io.py</c>), runs the C# engine, and maps results to comparison trees.</summary>
internal static class EngineRunner
{
    private static readonly string[] Known =
        ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State"];

    public static RowCell Cell(JsonElement obj, string name)
    {
        if (!obj.TryGetProperty(name, out var e))
        {
            return RowCell.Absent;
        }

        switch (e.ValueKind)
        {
            case JsonValueKind.Null:
                return RowCell.Null;
            case JsonValueKind.String:
                return RowCell.OfText(e.GetString()!);
            case JsonValueKind.Number:
                var raw = e.GetRawText();
                return raw.AsSpan().IndexOfAny('.', 'e', 'E') >= 0
                    ? RowCell.OfFloat(double.Parse(raw, NumberStyles.Float, CultureInfo.InvariantCulture))
                    : RowCell.OfInt(long.Parse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture));
            default:
                throw new PyUnsupportedException("Unsupported cell JSON " + e.ValueKind);
        }
    }

    public static PayrollRow Row(JsonElement o) => new(
        Cell(o, "Employee_ID"), Cell(o, "Worksite_ID"), Cell(o, "Entity_FEIN"), Cell(o, "Pay_Period_Start"), Cell(o, "Pay_Period_End"),
        Cell(o, "Pay_Date"), Cell(o, "Hours_Worked"), Cell(o, "Gross_Wages"), Cell(o, "Pay_Code"), Cell(o, "Work_State"));

    public static List<PayrollRow> Rows(JsonElement rows) => rows.EnumerateArray().Select(Row).ToList();

    private static PyNumber Num(JsonElement e)
    {
        var raw = e.GetRawText();
        return raw.AsSpan().IndexOfAny('.', 'e', 'E') >= 0
            ? PyNumber.OfFloat(double.Parse(raw, NumberStyles.Float, CultureInfo.InvariantCulture))
            : PyNumber.OfInt(long.Parse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture));
    }

    private static string[]? Strings(JsonElement p, string name) =>
        p.TryGetProperty(name, out var e) && e.ValueKind == JsonValueKind.Array ? e.EnumerateArray().Select(x => x.GetString()!).ToArray() : null;

    public static OneZeroMethodology Methodology(JsonElement? block)
    {
        var m = new OneZeroMethodology();
        if (block is not { ValueKind: JsonValueKind.Object } b)
        {
            return m;
        }

        foreach (var prop in b.EnumerateObject())
        {
            var v = prop.Value;
            m = prop.Name switch
            {
                "minimum_pay_period_days" => m with { MinimumPayPeriodDays = v.GetInt64() },
                "short_periods_excluded_from_numerator" => m with { ShortPeriodsExcludedFromNumerator = v.GetBoolean() },
                "pay_period_denominator_mode" => m with { PayPeriodDenominatorMode = v.GetString()! },
                "min_max_span_mode" => m with { MinMaxSpanMode = v.GetString()! },
                "count_zero_hour_periods" => m with { CountZeroHourPeriods = v.GetBoolean() },
                "average_decimals" => m with { AverageDecimals = v.GetInt32() },
                "maximum_weeks_without_review" => m with { MaximumWeeksWithoutReview = Num(v) },
                "exclude_off_cycle_periods" => m with { ExcludeOffCyclePeriods = v.GetBoolean() },
                _ => throw new PyUnsupportedException("Unknown methodology key " + prop.Name),
            };
        }

        return m;
    }

    public static OneZeroPack Pack(JsonElement p)
    {
        (PyNumber, PyNumber)? band = null;
        if (p.TryGetProperty("pt_band_hours", out var bandEl) && bandEl.ValueKind == JsonValueKind.Array)
        {
            band = (Num(bandEl[0]), Num(bandEl[1]));
        }

        PyNumber? weight = p.TryGetProperty("pt_weight", out var w) && w.ValueKind == JsonValueKind.Number ? Num(w) : null;
        return new OneZeroPack
        {
            MinWeeklyHours = Num(p.GetProperty("min_weekly_hours")),
            MinWeeklyWages = Num(p.GetProperty("min_weekly_wages")),
            Citation = p.TryGetProperty("citation", out var c) ? c.GetString() ?? string.Empty : string.Empty,
            PtBandHours = band,
            PtWeight = weight,
            MeasuringDate = p.TryGetProperty("measuring_date", out var md) ? (md.ValueKind == JsonValueKind.Null ? null : md.GetString()) : "last_day",
            IncludedPayCodes = Strings(p, "included_pay_codes"),
            ExcludedPayCodes = Strings(p, "excluded_pay_codes"),
            Methodology = Methodology(p.TryGetProperty("methodology", out var mm) ? mm : null),
        };
    }

    private static DateOnly D(JsonElement e) => DateOnly.ParseExact(e.GetString()!, "yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static (DateOnly, DateOnly)? Window(JsonElement p, string name) =>
        p.TryGetProperty(name, out var w) && w.ValueKind == JsonValueKind.Array ? (D(w[0]), D(w[1])) : null;

    public static EngineOutcome Execute(JsonElement request, List<PayrollRow>? datasetRows = null)
    {
        try
        {
            return ExecuteCore(request, datasetRows);
        }
        catch (PyException e)
        {
            return new EngineOutcome(false, null, null, e.PythonType);
        }
        catch (PyUnsupportedException e)
        {
            return new EngineOutcome(false, null, null, "UNSUPPORTED:" + e.Message);
        }
#pragma warning disable CA1031 // A non-Python exception is a port defect and must be reported, not thrown past the harness.
        catch (Exception e)
        {
            return new EngineOutcome(false, null, null, "CSHARP:" + e.GetType().Name + ":" + e.Message);
        }
#pragma warning restore CA1031
    }

    private static EngineOutcome ExecuteCore(JsonElement req, List<PayrollRow>? datasetRows)
    {
        var op = req.GetProperty("op").GetString()!;
        var p = req.TryGetProperty("params", out var pe) ? pe : default;
        var rows = datasetRows ?? (req.TryGetProperty("rows", out var re) ? Rows(re) : []);
        object? result;
        object? trail = null;
        switch (op)
        {
            case "pay_period":
            case "min_max":
                var recorder = p.TryGetProperty("with_trail", out var wt) && wt.GetBoolean()
                    ? new TrailRecorder(p.TryGetProperty("trail_title", out var tt) ? tt.GetString()! : string.Empty, p.TryGetProperty("trail_citation", out var tc) ? tc.GetString()! : string.Empty)
                    : null;
                var pack = Pack(p.GetProperty("pack"));
                var fm = p.TryGetProperty("fiscal_year_end_month", out var fme) ? fme.GetInt64() : 12;
                var res = op == "pay_period"
                    ? PayPeriodMethod.Run(rows, p.GetProperty("tax_year").GetInt64(), D(p.GetProperty("analysis_start_month")), pack, fm, Window(p, "fiscal_window"), recorder)
                    : MinMaxMethod.Run(rows, p.GetProperty("tax_year").GetInt64(), D(p.GetProperty("analysis_start_month")), pack, fm, Window(p, "fiscal_window"), recorder);
                result = ResultMapper.Map(res);
                trail = recorder?.ToDict();
                break;
            case "preprocess":
                var rec2 = p.TryGetProperty("with_trail", out var wt2) && wt2.GetBoolean() ? new TrailRecorder() : null;
                var fm2 = p.TryGetProperty("fiscal_year_end_month", out var f2) ? f2.GetInt64() : 12;
                var meth = Methodology(p.TryGetProperty("methodology", out var me) ? me : null);
                var outRows = OneZeroPreprocessing.Preprocess(rows, p.GetProperty("tax_year").GetInt64(), fm2, Window(p, "fiscal_window"), meth, rec2);
                result = ResultMapper.MapRows(outRows);
                trail = rec2?.ToDict();
                break;
            case "first_measurable_month":
                var w = Window(p, "window")!.Value;
                result = Iso(OneZeroCalendar.FirstMeasurableMonth(rows, w.Item1, w.Item2));
                break;
            case "unreachable_months":
                result = OneZeroCalendar.UnreachableMonths(rows, p.GetProperty("months").EnumerateArray().Select(D).ToList()).Select(i => (object?)i).ToList();
                break;
            case "apply_pay_code_policy":
                result = ResultMapper.MapRows(OneZeroEligibility.ApplyPayCodePolicy(rows, Pack(p.GetProperty("pack"))));
                break;
            case "average_headcount":
                result = Headcount.AverageHeadcount(rows, p.GetProperty("state").GetString()!, p.GetProperty("tax_year").GetInt64(), Pack(p.GetProperty("pack")), Window(p, "window"));
                break;
            case "rows_for_state_year":
                result = ResultMapper.MapRows(Headcount.RowsForStateYear(rows, p.GetProperty("state").GetString()!, p.GetProperty("tax_year").GetInt64(), Window(p, "window")));
                break;
            case "row_states":
                result = rows.Select(r => (object?)Headcount.RowState(r)).ToList();
                break;
            case "states_present":
                result = Headcount.StatesPresent(rows).Select(s => (object?)s).ToList();
                break;
            case "helper":
                result = Helpers.Run(p);
                break;
            case "fiscal":
                result = Helpers.Fiscal(p);
                break;
            case "floors":
                var floors = new StatutoryFloors(
                    p.GetProperty("program_code").GetString()!, p.GetProperty("tax_year").GetInt64(), Num(p.GetProperty("min_weekly_hours")), Num(p.GetProperty("min_weekly_wages")),
                    (PyDict)JsonTree.Read(p.GetProperty("basis"))!, (PyDict)JsonTree.Read(p.GetProperty("provenance"))!, p.GetProperty("pack_file").GetString()!);
                result = new PyDict().Add("as_dict", floors.AsDict()).Add("prototype_verify", floors.PrototypeVerify).Add("program_name", StatutoryFloors.ProgramName(floors.PackFile));
                break;
            default:
                throw new PyUnsupportedException("Unknown op " + op);
        }

        return new EngineOutcome(true, result, trail, null);
    }

    internal static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    internal static IReadOnlyList<string> KnownColumns => Known;
}
