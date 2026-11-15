using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Designations;

public sealed partial class DesignationRegistry
{
    /// <summary>Python <c>DEFAULT</c> base year of <c>detect_designation_splits</c>.</summary>
    public const long DefaultBaseYear = 2021;

    /// <summary>
    /// Python <c>detect_designation_splits</c> (CALC-08): per-worksite timelines for <paramref name="state"/>, flagging the sites whose designation changed
    /// between <paramref name="baseYear"/> and <paramref name="taxYear"/> (a parallel-calculation trigger). Records one step into the ambient trail.
    /// </summary>
    /// <param name="state">The state code (upper-cased; sites are those whose id starts with <c>STATE_</c>).</param>
    /// <param name="taxYear">The analysis year.</param>
    /// <param name="baseYear">The base year.</param>
    /// <returns>The report tree.</returns>
    public PyDict DetectDesignationSplits(string state, long taxYear, long baseYear = DefaultBaseYear)
    {
        ArgumentNullException.ThrowIfNull(state);
        var stateU = PyStr.Upper(state);
        var sites = new List<object?>();
        var splitCount = 0L;
        foreach (var (wsid, history) in PySort.Sorted(_legacy, kv => kv.Key, PyStr.Comparer))
        {
            if (!wsid.StartsWith(stateU + "_", StringComparison.Ordinal))
            {
                continue;
            }

            var baseEntry = history.FirstOrDefault(h => YearOf(h) <= baseYear) ?? (history.Count > 0 ? history[0] : null);
            var current = history.Reverse().FirstOrDefault(h => YearOf(h) <= taxYear);
            var changed = baseEntry is not null && current is not null && ProximityCoerce.Truthy(baseEntry) && ProximityCoerce.Truthy(current)
                && !PyEquality.Equal(baseEntry["designation"], current["designation"]);
            var parallel = new List<object?>();
            if (changed)
            {
                splitCount++;
                parallel = ParallelCalcs(baseEntry!, current!, taxYear, baseYear);
            }

            sites.Add(new PyDict()
                .Add("worksite_id", wsid).Add("base_designation", baseEntry).Add("current_designation", current)
                .Add("designation_changed", changed).Add("parallel_calcs", parallel));
        }

        Record(stateU, taxYear, baseYear, sites.Count, splitCount);
        var report = new PyDict().Add("_roadmap_tag", "L2").Add("_story", "CALC-08");
        foreach (var kv in DiscMeta())
        {
            report.Add(kv.Key, kv.Value);
        }

        return report.Add("state", stateU).Add("tax_year", taxYear).Add("base_year", baseYear).Add("site_count", (long)sites.Count)
            .Add("parallel_calc_site_count", splitCount).Add("sites", sites);
    }

    private static List<object?> ParallelCalcs(PyDict baseEntry, PyDict current, long taxYear, long baseYear) =>
    [
        new PyDict().Add("stream", "surviving_base_designation").Add("designation", baseEntry["designation"]).Add("tier", baseEntry["tier"])
            .Add("min_new_jobs", baseEntry["min_new_jobs"]).Add("window", new List<object?> { baseYear, taxYear })
            .Add("note", "Jobs created under the original designation continue their tranches."),
        new PyDict().Add("stream", "new_designation_net_new").Add("designation", current["designation"]).Add("tier", current["tier"])
            .Add("min_new_jobs", current["min_new_jobs"]).Add("window", new List<object?> { taxYear, taxYear + 4 })
            .Add("note", "Net-new created in the change year is a separate analysis under the new minimum."),
    ];

    private static void Record(string stateU, long taxYear, long baseYear, int sites, long splitCount) =>
        TrailContext.Current?.Record(
            $"{stateU}: detect designation changes ({baseYear}->{taxYear})",
            new PyDict().Add("sites", (long)sites),
            "flag site where designation(base_year) != designation(tax_year)",
            new PyDict().Add("parallel_calc_sites", splitCount),
            $"GA designation-change parallel-calc rule (pending GA form — {DiscRef})");
}
