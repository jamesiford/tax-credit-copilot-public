using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Trend;

/// <summary>
/// The per-unit multi-year trend (Python <c>tools/unit_trend.py</c>): reshapes the engine's (unit x FEIN) monthly summary into a per-unit yearly series
/// and hands each series to the frozen-base-year engine. No statutory math of its own.
/// </summary>
public static partial class UnitTrendTools
{
    /// <summary>Python <c>MONTHS_IN_YEAR</c>.</summary>
    public const int MonthsInYear = 12;

    /// <summary>Python <c>STATUS_BASE</c>.</summary>
    public const string StatusBase = "base";

    /// <summary>Python <c>STATUS_ABOVE</c>.</summary>
    public const string StatusAbove = "above_minimum";

    /// <summary>Python <c>STATUS_BELOW</c>.</summary>
    public const string StatusBelow = "below_minimum";

    /// <summary>Python <c>STATUS_PARTIAL</c>.</summary>
    public const string StatusPartial = "partial";

    /// <summary>Python <c>STATUS_NO_DATA</c>.</summary>
    public const string StatusNoData = "no_data";

    /// <summary>Python <c>STATUS_BEFORE_BASE</c> (WI-21): a complete year before the chosen base, never measured against it.</summary>
    public const string StatusBeforeBase = "before_base";

    /// <summary>Python <c>STATUS_IN_PROGRESS</c>: an open year, read on its closed months and not yet priced.</summary>
    public const string StatusInProgress = "in_progress";

    /// <summary>Python <c>aggregate_units</c>: collapses the engine's (unit x FEIN) summary to unit grain, sorted by unit id.</summary>
    /// <param name="summaryRows">The summary rows (<c>unit_id</c> or <c>Worksite_ID</c>, <c>fein</c> or <c>Entity_FEIN</c>, <c>month_totals</c>).</param>
    /// <returns>One dictionary per unit.</returns>
    public static IReadOnlyList<PyDict> AggregateUnits(IEnumerable<PyDict> summaryRows)
    {
        ArgumentNullException.ThrowIfNull(summaryRows);
        var byUnit = new OrderedMap<string, (List<string> Feins, double[] Months)>();
        foreach (var row in summaryRows)
        {
            var unitId = ProximityCoerce.Str(First(row, "unit_id", "Worksite_ID"));
            var fein = ProximityCoerce.Str(First(row, "fein", "Entity_FEIN"));
            var months = MonthValues(row);
            if (!byUnit.TryGetValue(unitId, out var bucket))
            {
                bucket = ([], new double[MonthsInYear]);
                byUnit.Set(unitId, bucket);
            }

            if (fein.Length > 0 && !bucket.Feins.Contains(fein, StringComparer.Ordinal))
            {
                bucket.Feins.Add(fein);
            }

            for (var i = 0; i < Math.Min(months.Count, MonthsInYear); i++)
            {
                bucket.Months[i] += months[i];
            }
        }

        var units = byUnit.Select(kv => UnitRow(kv.Key, kv.Value.Feins, kv.Value.Months)).ToList();
        return PySort.Sorted(units, u => (string)u["unit_id"]!, PyStr.Comparer);
    }

    /// <summary>Python <c>build_unit_series</c>: pivots <c>{tax_year: [unit rows]}</c> into <c>{unit_id: {tax_year: unit row}}</c>.</summary>
    /// <param name="perYearUnits">The unit rows by tax year (insertion order is the iteration order).</param>
    /// <returns>The pivot; a unit missing from a year is absent, never zero-filled.</returns>
    /// <exception cref="PyKeyError">When a unit row has no <c>unit_id</c>.</exception>
    public static OrderedMap<string, OrderedMap<long, PyDict>> BuildUnitSeries(OrderedMap<long, IReadOnlyList<PyDict>> perYearUnits)
    {
        ArgumentNullException.ThrowIfNull(perYearUnits);
        var series = new OrderedMap<string, OrderedMap<long, PyDict>>();
        foreach (var (taxYear, units) in perYearUnits)
        {
            foreach (var unit in units)
            {
                var id = ProximityCoerce.Str(unit["unit_id"]);
                if (!series.TryGetValue(id, out var years))
                {
                    years = new OrderedMap<long, PyDict>();
                    series.Set(id, years);
                }

                years.Set(taxYear, Copy(unit));
            }
        }

        return series;
    }

    /// <summary>Python <c>infer_base_year</c>: the unit's earliest year of complete payroll, completeness judged against the REACHABLE months.</summary>
    /// <param name="unitYears">The unit's rows by tax year.</param>
    /// <param name="reachableByYear">The measuring months a pay period reaches, by year (<c>null</c> or empty means twelve for every year).</param>
    /// <returns>The base year, or <c>null</c> when the unit has no years.</returns>
    public static long? InferBaseYear(OrderedMap<long, PyDict> unitYears, OrderedMap<long, long>? reachableByYear = null)
    {
        ArgumentNullException.ThrowIfNull(unitYears);
        if (unitYears.Count == 0)
        {
            return null;
        }

        // Why: a calendar filer whose last December period ends on the 15th has no December measuring date; judging it against twelve pushed the base a year later.
        foreach (var (year, unit) in unitYears.OrderBy(kv => kv.Key))
        {
            var reachable = reachableByYear is not null && reachableByYear.TryGetValue(year, out var r) ? r : MonthsInYear;
            var raw = Get(unit, "months_with_headcount");
            var months = ProximityCoerce.Truthy(raw) ? ToBig(ProximityCoerce.ToInt(raw)) : BigInteger.Zero;
            if (months >= reachable)
            {
                return year;
            }
        }

        return unitYears.Keys.Min();
    }

    /// <summary>Python <c>unit_status</c>: one reading per unit-year, decided in a single place.</summary>
    /// <param name="taxYear">The year.</param>
    /// <param name="baseYear">The unit's base year, if any.</param>
    /// <param name="qualified">Whether the year cleared the threshold.</param>
    /// <param name="monthsWithHeadcount">Months with any headcount.</param>
    /// <param name="monthsReachable">Months a pay period reaches (default twelve).</param>
    /// <returns>One of the <c>Status*</c> constants.</returns>
    public static string UnitStatus(long taxYear, long? baseYear, bool qualified, long monthsWithHeadcount, long monthsReachable = MonthsInYear)
    {
        if (monthsWithHeadcount <= 0)
        {
            return StatusNoData;
        }

        if (baseYear is not null && taxYear == baseYear)
        {
            return StatusBase;
        }

        // A complete year before a chosen base was never measured; calling it "below minimum" would paint a shortfall that did not happen.
        if (baseYear is not null && taxYear < baseYear && monthsWithHeadcount >= monthsReachable)
        {
            return StatusBeforeBase;
        }

        if (monthsWithHeadcount < monthsReachable)
        {
            return StatusPartial;
        }

        return qualified ? StatusAbove : StatusBelow;
    }

    /// <summary>Python <c>unit_trend</c>: runs the frozen-base-year engine over one unit's yearly averages.</summary>
    /// <param name="unitYears">The unit's rows by tax year (only <c>average_headcount</c> is read).</param>
    /// <param name="state">The state code.</param>
    /// <param name="baseYear">The unit's base year.</param>
    /// <param name="settings">The threshold, rate, window and per-year statute.</param>
    /// <returns>The engine result.</returns>
    public static BaseYearResult UnitTrend(OrderedMap<long, PyDict> unitYears, string state, long baseYear, BaseYearSettings settings)
    {
        ArgumentNullException.ThrowIfNull(unitYears);
        var yearly = new OrderedMap<long, PyNumber>();
        foreach (var (year, unit) in unitYears)
        {
            var v = Get(unit, "average_headcount");
            yearly.Set(year, PyNumber.OfFloat(ProximityCoerce.Truthy(v) ? ProximityCoerce.ToFloat(v) : 0.0));
        }

        return BaseYearEngine.ComputeBaseYearTranches(state, yearly, baseYear, settings);
    }

    private static object? Get(PyDict d, string key) => d.TryGetValue(key, out var v) ? v : null;

    /// <summary>Python <c>row.get(a) or row.get(b) or ""</c>.</summary>
    private static object First(PyDict row, string a, string b)
    {
        var x = Get(row, a);
        if (ProximityCoerce.Truthy(x))
        {
            return x!;
        }

        var y = Get(row, b);
        return ProximityCoerce.Truthy(y) ? y! : string.Empty;
    }

    private static BigInteger ToBig(object v) => v is BigInteger b ? b : (long)v;

    private static PyDict Copy(PyDict source) => source.Aggregate(new PyDict(), (d, kv) => d.Set(kv.Key, kv.Value));

    private static List<double> MonthValues(PyDict row)
    {
        var raw = Get(row, "month_totals");
        if (!ProximityCoerce.Truthy(raw))
        {
            return [];
        }

        return raw is List<object?> list
            ? list.Select(v => ProximityCoerce.ToFloat(v)).ToList()
            : throw new PyUnsupportedException("month_totals is not a list");
    }

    private static PyDict UnitRow(string unitId, List<string> feins, double[] months)
    {
        var totals = months.Select(v => PyRound.Round(v, 2)).ToList();
        var total = PyRound.Round(PySum.Sum(totals), 2);
        return new PyDict()
            .Add("unit_id", unitId)
            .Add("feins", PySort.Sorted(feins, f => f, PyStr.Comparer).Select(f => (object?)f).ToList())
            .Add("month_totals", totals.Select(v => (object?)v).ToList())
            .Add("total", total)
            .Add("average_headcount", PyRound.Round(total / MonthsInYear, 2))
            .Add("months_with_headcount", (long)totals.Count(v => v > 0));
    }
}
