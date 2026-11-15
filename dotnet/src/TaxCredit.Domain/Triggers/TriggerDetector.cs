using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Triggers;

/// <summary>
/// Python <c>tools/triggers.py</c> <c>detect_triggers</c>: diffs two pay-period snapshots and emits the opportunity flags
/// (headcount spike, wage increase, new FEIN, new jurisdiction).
/// </summary>
public static class TriggerDetector
{
    /// <summary>The default <c>headcount_spike_min</c>: 5 (an int).</summary>
    public static PyNumber DefaultHeadcountSpikeMin { get; } = PyNumber.OfInt(5);

    /// <summary>The default <c>wage_increase_min_pct</c>: 0.10 (a float).</summary>
    public static PyNumber DefaultWageIncreaseMinPct { get; } = PyNumber.OfFloat(0.10);

    /// <summary>Python <c>detect_triggers(prior_rows, current_rows, *, headcount_spike_min=5, wage_increase_min_pct=0.10)</c>.</summary>
    /// <param name="priorRows">The earlier snapshot.</param>
    /// <param name="currentRows">The later snapshot.</param>
    /// <param name="headcountSpikeMin">Smallest year-over-year employee gain that is a spike (<c>null</c> is the default 5).</param>
    /// <param name="wageIncreaseMinPct">Smallest fractional rise in average hourly wage that is a flag (<c>null</c> is the default 0.10).</param>
    /// <returns>The triggers in emission order: per-unit spikes and wage rises, then new FEINs, then new jurisdictions.</returns>
    public static List<PyDict> Detect(IReadOnlyList<PyDict> priorRows, IReadOnlyList<PyDict> currentRows, PyNumber? headcountSpikeMin = null, PyNumber? wageIncreaseMinPct = null)
    {
        ArgumentNullException.ThrowIfNull(priorRows);
        ArgumentNullException.ThrowIfNull(currentRows);
        var spikeMin = headcountSpikeMin ?? DefaultHeadcountSpikeMin;
        var wageMin = wageIncreaseMinPct ?? DefaultWageIncreaseMinPct;
        var triggers = new List<PyDict>();
        var prior = UnitAggregation.Aggregate(priorRows).ToDictionary(p => p.Unit, p => p.Slot, StringComparer.Ordinal);
        foreach (var (unit, current) in UnitAggregation.Aggregate(currentRows))
        {
            if (unit.Length == 0)
            {
                continue;
            }

            var state = PyStr.Prefix(unit, 2);
            prior.TryGetValue(unit, out var priorSlot);
            Spike(triggers, unit, state, priorSlot is null ? 0 : priorSlot.Employees.Count, current.Employees.Count, spikeMin);
            if (priorSlot is not null && priorSlot.TotalHours > 0 && current.TotalHours > 0)
            {
                WageRise(triggers, unit, state, priorSlot, current, wageMin);
            }
        }

        NewFeins(triggers, priorRows, currentRows);
        NewJurisdictions(triggers, priorRows, currentRows);
        return triggers;
    }

    private static void Spike(List<PyDict> triggers, string unit, string state, int priorEmp, int currEmp, PyNumber min)
    {
        long delta = currEmp - priorEmp;
        if (!PyNumCompare.AtLeast(delta, min))
        {
            return;
        }

        triggers.Add(new PyDict()
            .Add("type", "headcount_spike")
            .Add("jurisdiction", state)
            .Add("unit", unit)
            .Add("prior_headcount", (long)priorEmp)
            .Add("current_headcount", (long)currEmp)
            .Add("delta", delta)
            .Add("severity", delta >= 10 ? "high" : "medium")
            .Add("message", $"Headcount spike at {unit}: {priorEmp} -> {currEmp} employees (+{delta}). Eligible for One/Zero recompute against {state} rule pack."));
    }

    private static void WageRise(List<PyDict> triggers, string unit, string state, UnitSlot priorSlot, UnitSlot current, PyNumber min)
    {
        var priorAvg = PyArith.TrueDiv(priorSlot.TotalWages, priorSlot.TotalHours);
        var currAvg = PyArith.TrueDiv(current.TotalWages, current.TotalHours);
        if (!(priorAvg > 0))
        {
            return;
        }

        var pct = PyArith.TrueDiv(currAvg - priorAvg, priorAvg);
        if (!PyNumCompare.AtLeast(pct, min))
        {
            return;
        }

        triggers.Add(new PyDict()
            .Add("type", "wage_increase")
            .Add("jurisdiction", state)
            .Add("unit", unit)
            .Add("prior_avg_hourly", PyRound.Round(priorAvg, 2))
            .Add("current_avg_hourly", PyRound.Round(currAvg, 2))
            .Add("delta_pct", PyRound.Round(pct, 3))
            .Add("severity", "medium")
            .Add("message", $"Avg hourly wage at {unit} rose from ${PyFormat.Fixed(priorAvg, 2, grouping: true)} to ${PyFormat.Fixed(currAvg, 2, grouping: true)} (+{Percent(pct)}); may push borderline employees over the One/Zero weekly-wage floor."));
    }

    // Python `f"{x:.1%}"`: the value times 100 in a double, fixed to one place, then a percent sign.
    private static string Percent(double x) => PyFormat.Fixed(x * 100, 1) + "%";

    private static void NewFeins(List<PyDict> triggers, IReadOnlyList<PyDict> priorRows, IReadOnlyList<PyDict> currentRows)
    {
        var priorFeins = Feins(priorRows).Select(SetMember).ToHashSet();
        var added = Feins(currentRows).Where(f => !priorFeins.Contains(SetMember(f))).ToList();
        foreach (var fein in SortedFeins(added))
        {
            var states = currentRows
                .Where(r => Equals(r.TryGetValue("Entity_FEIN", out var f) ? f : null, fein) && r.TryGetValue("Worksite_ID", out var w) && ProximityCoerce.Truthy(w))
                .Select(r => PyStr.Prefix((string)r["Worksite_ID"]!, 2))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(s => s, PyStr.Comparer)
                .ToList();
            var where = states.Count > 0 ? states[0] : "the latest snapshot";
            triggers.Add(new PyDict()
                .Add("type", "new_fein")
                .Add("jurisdiction", states.Count > 0 ? states[0] : null)
                .Add("fein", fein)
                .Add("severity", "high")
                .Add("message", $"New legal entity FEIN {ProximityCoerce.Str(fein)} appeared in {where}; may require a new rule-pack pinning and a separate compliance filing per entity."));
        }
    }

    // Python `{r.get("Entity_FEIN", "") for r in rows} - {""}`, as distinct cells in first-seen order.
    private static List<object?> Feins(IReadOnlyList<PyDict> rows)
    {
        var seen = new HashSet<object>();
        var cells = new List<object?>();
        foreach (var r in rows)
        {
            var cell = r.TryGetValue("Entity_FEIN", out var f) ? f : string.Empty;
            if (!(cell is string { Length: 0 }) && seen.Add(SetMember(cell)))
            {
                cells.Add(cell);
            }
        }

        return cells;
    }

    private static object SetMember(object? cell) => UnitAggregation.SetKey(cell);

    // Python `sorted(set)`. A set of one sorts trivially; text sorts by code point; ints numerically. Mixed members raise a TypeError whose
    // wording depends on the set's hash order in CPython (finding CQ-04), so this reports the str-first wording and no golden pins it.
    private static IEnumerable<object?> SortedFeins(List<object?> cells)
    {
        if (cells.Count <= 1)
        {
            return cells;
        }

        if (cells.All(c => c is string))
        {
            return cells.OrderBy(c => (string)c!, PyStr.Comparer);
        }

        if (cells.All(c => c is long))
        {
            return cells.OrderBy(c => (long)c!);
        }

        throw new PyTypeError("'<' not supported between instances of '" + ProximityCoerce.TypeName(cells[1]) + "' and '" + ProximityCoerce.TypeName(cells[0]) + "'");
    }

    private static void NewJurisdictions(List<PyDict> triggers, IReadOnlyList<PyDict> priorRows, IReadOnlyList<PyDict> currentRows)
    {
        var priorStates = States(priorRows);
        foreach (var st in States(currentRows).Where(s => !priorStates.Contains(s)).OrderBy(s => s, PyStr.Comparer))
        {
            triggers.Add(new PyDict()
                .Add("type", "new_jurisdiction")
                .Add("jurisdiction", st)
                .Add("severity", "high")
                .Add("message", $"New jurisdiction {st} appeared in the latest snapshot; rule-pack discovery should evaluate any {st} state credits that may apply."));
        }
    }

    // Python `{r.get("Worksite_ID", "")[:2] for r in rows if len(r.get("Worksite_ID", "")) >= 2}`; the aggregation has already
    // rejected every non-string worksite id, so only text reaches here.
    private static HashSet<string> States(IReadOnlyList<PyDict> rows) => rows
        .Select(r => r.TryGetValue("Worksite_ID", out var w) ? (string)w! : string.Empty)
        .Where(w => PyStr.Length(w) >= 2)
        .Select(w => PyStr.Prefix(w, 2))
        .ToHashSet(StringComparer.Ordinal);
}
