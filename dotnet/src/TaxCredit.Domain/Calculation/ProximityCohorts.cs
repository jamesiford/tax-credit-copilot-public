using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

public static partial class Proximity
{
    private const string NearMissNote =
        "Additional hours are priced at each employee's own implied hourly "
        + "rate (total wages / total hours), so the figure reflects the wages "
        + "those hours would also earn. Employees paid below the effective "
        + "hourly floor are flagged: for them the wage test binds harder than "
        + "the hours test, and a pay rise rather than a longer week is the lever.";

    private const string FragileNote =
        "Cushion is the SMALLER of the two floors' headroom, because "
        + "eligibility needs both cleared — an employee falls out the moment "
        + "either is breached. This describes a completed year: it is what "
        + "would have to change to lose these jobs, not a forecast that they "
        + "will be lost.";

    /// <summary>The ineligible population ranked by how little it would take to qualify (<c>near_miss_cohort</c>).</summary>
    /// <param name="averages">Rows of <c>all_averages</c>.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="withinWeeklyHours">Band in additional weekly hours (default 5.0); echoed with its int/float type.</param>
    /// <param name="limit">Cohort size; <c>null</c> or 0 means all (a negative value slices like Python).</param>
    /// <param name="decimals">Places to round to.</param>
    /// <param name="population">Whole-client counts that override the counts taken over <paramref name="averages"/> (a non-empty dict).</param>
    /// <returns>The cohort tree, keys in Python order.</returns>
    public static PyDict NearMissCohort(
        IReadOnlyList<PyDict> averages,
        StatutoryFloors floors,
        PyNumber? withinWeeklyHours = null,
        long? limit = null,
        int decimals = 2,
        PyDict? population = null)
    {
        ArgumentNullException.ThrowIfNull(averages);
        ArgumentNullException.ThrowIfNull(floors);
        var within = withinWeeklyHours ?? PyNumber.OfFloat(5.0);
        var assessed = averages.Select(a => AssessEmployee(a, floors, decimals)).ToList();
        var ineligible = assessed.Where(a => !(bool)a["eligible"]!).ToList();

        var modes = new PyDict().Add("hours_only", 0L).Add("wages_only", 0L).Add("both", 0L);
        foreach (var row in ineligible)
        {
            var mode = (string)row["failure_mode"]!;
            // "none" (a recorded-ineligible row that clears both floors) is added as a fourth key, as Python's modes.get does.
            modes.Set(mode, (modes.TryGetValue(mode, out var n) ? (long)n! : 0L) + 1);
        }

        var reachable = ineligible.Where(r => Lever(r, "additional_weekly_hours") is { } h && h <= ProximityCoerce.ToFloat(within)).ToList();
        reachable = SortByLever(reachable, "additional_weekly_hours");
        var cohort = Take(reachable, limit);
        var usePopulation = population is { Count: > 0 };
        var floorsTree = FloorsTree(floors, decimals, threshold: true);

        return new PyDict()
            .Add("floors", floorsTree)
            .Add("band_weekly_hours", TrailValues.Of(within))
            .Add("evaluated", usePopulation ? ProximityCoerce.ToInt(Req(population!, "evaluated")) : (long)assessed.Count)
            .Add("eligible", usePopulation ? ProximityCoerce.ToInt(Req(population!, "eligible")) : (long)(assessed.Count - ineligible.Count))
            .Add("ineligible", usePopulation ? ProximityCoerce.ToInt(Req(population!, "ineligible")) : (long)ineligible.Count)
            // Rows where the recorded verdict and today's floors disagree: the ruler moved after the run.
            .Add("verdict_disagreements", (long)assessed.Count(r => (bool)r["verdict_disagrees"]!))
            .Add("failure_modes", usePopulation ? CopyDict(Req(population!, "failure_modes")) : modes)
            .Add("within_band", (long)reachable.Count)
            .Add("rate_limited_in_band", (long)reachable.Count(r => (bool)r["rate_limited"]!))
            .Add("exceeds_plausible_week_in_band", (long)reachable.Count(r => (bool)r["exceeds_plausible_week"]!))
            .Add("returned", (long)cohort.Count)
            .Add("cohort", cohort.Cast<object?>().ToList())
            .Add("method_note", NearMissNote);
    }

    /// <summary>Qualifying employees ranked by how little it would take to lose them (<c>fragile_cohort</c>); the input is taken as the ELIGIBLE population.</summary>
    /// <param name="averages">Rows of the eligible population.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="withinWeeklyHours">Band in weekly hours (default 5.0).</param>
    /// <param name="limit">Cohort size; <c>null</c> or 0 means all.</param>
    /// <param name="decimals">Places to round to.</param>
    /// <param name="population">Whole-client counts that override the counts taken over <paramref name="averages"/>.</param>
    /// <returns>The cohort tree, keys in Python order.</returns>
    public static PyDict FragileCohort(
        IReadOnlyList<PyDict> averages,
        StatutoryFloors floors,
        PyNumber? withinWeeklyHours = null,
        long? limit = null,
        int decimals = 2,
        PyDict? population = null)
    {
        ArgumentNullException.ThrowIfNull(averages);
        ArgumentNullException.ThrowIfNull(floors);
        var within = withinWeeklyHours ?? PyNumber.OfFloat(5.0);
        var assessed = averages.Select(a => Fragility(a, floors, decimals)).ToList();
        var reachable = assessed.Where(a => Lever(a, "weekly_hours_to_lose") is { } h && h <= ProximityCoerce.ToFloat(within)).ToList();
        reachable = SortByLever(reachable, "weekly_hours_to_lose");
        var cohort = Take(reachable, limit);
        var usePopulation = population is { Count: > 0 };

        return new PyDict()
            .Add("band_weekly_hours", TrailValues.Of(within))
            .Add("eligible", usePopulation ? ProximityCoerce.ToInt(Req(population!, "eligible")) : (long)assessed.Count)
            .Add("evaluated", usePopulation ? ProximityCoerce.ToInt(Req(population!, "evaluated")) : (long)assessed.Count)
            .Add("within_band", (long)reachable.Count)
            // Jobs, not people: a part-time band carries a fractional weight. sum() is the 3.12 compensated algorithm.
            .Add("jobs_at_risk", ProximityCoerce.RoundHalfUp(PySum.Sum(reachable.Select(r => (double)r["weight"]!).ToList()), decimals))
            .Add("binding_floors", new PyDict()
                .Add("hours", (long)reachable.Count(r => (string)r["binding_floor"]! == "hours"))
                .Add("wages", (long)reachable.Count(r => (string)r["binding_floor"]! == "wages")))
            .Add("returned", (long)cohort.Count)
            .Add("cohort", cohort.Cast<object?>().ToList())
            .Add("floors", FloorsTree(floors, decimals, threshold: false))
            .Add("method_note", FragileNote);
    }

    /// <summary>How many become eligible at each band, and how many of those at a plausible week (<c>band_curve</c>).</summary>
    /// <param name="averages">Rows of <c>all_averages</c>.</param>
    /// <param name="floors">The year's floors.</param>
    /// <param name="bands">Notches; defaults to <see cref="BandCurveHours"/>. Each is echoed with its int/float type.</param>
    /// <param name="decimals">Places to round to.</param>
    /// <returns>One tree per band.</returns>
    public static List<PyDict> BandCurve(IReadOnlyList<PyDict> averages, StatutoryFloors floors, IReadOnlyList<PyNumber>? bands = null, int decimals = 2)
    {
        ArgumentNullException.ThrowIfNull(averages);
        ArgumentNullException.ThrowIfNull(floors);
        var notches = bands ?? BandCurveHours.Select(PyNumber.OfFloat).ToList();
        var assessed = averages.Select(a => AssessEmployee(a, floors, decimals)).ToList();
        var ineligible = assessed.Where(a => !(bool)a["eligible"]! && a["additional_weekly_hours"] is not null).ToList();
        return notches.Select(band =>
        {
            var b = ProximityCoerce.ToFloat(band);
            return new PyDict()
                .Add("within_weekly_hours", TrailValues.Of(band))
                .Add("employees", (long)ineligible.Count(r => Lever(r, "additional_weekly_hours")!.Value <= b))
                .Add("plausible", (long)ineligible.Count(r => Lever(r, "additional_weekly_hours")!.Value <= b && !(bool)r["exceeds_plausible_week"]!));
        }).ToList();
    }

    private static double? Lever(PyDict row, string key) => (double?)row[key];

    /// <summary>Python <c>list.sort(key=lambda r: (lever, str(employee_id)))</c>: stable, ties broken by the id's text in code-point order.</summary>
    private static List<PyDict> SortByLever(List<PyDict> rows, string key) =>
        PySort.Sorted(rows, r => (Lever: Lever(r, key)!.Value, Id: ProximityCoerce.Str(r["employee_id"])), Comparer<(double Lever, string Id)>.Create(CompareKeys));

    private static int CompareKeys((double Lever, string Id) x, (double Lever, string Id) y) =>
        x.Lever < y.Lever ? -1 : x.Lever > y.Lever ? 1 : PyStr.Compare(x.Id, y.Id);

    /// <summary>Python <c>reachable[:limit] if limit else reachable</c> (a negative limit drops that many from the end).</summary>
    private static List<PyDict> Take(List<PyDict> rows, long? limit)
    {
        if (limit is null or 0)
        {
            return rows;
        }

        var end = limit.Value >= 0 ? Math.Min(limit.Value, rows.Count) : Math.Max(0, rows.Count + limit.Value);
        return rows.Take((int)end).ToList();
    }

    private static PyDict FloorsTree(StatutoryFloors floors, int decimals, bool threshold)
    {
        var tree = new PyDict()
            .Add("program_code", floors.ProgramCode)
            .Add("tax_year", floors.TaxYear)
            .Add("minimum_average_weekly_hours", TrailValues.Of(floors.MinWeeklyHours))
            .Add("minimum_average_weekly_wages_usd", TrailValues.Of(floors.MinWeeklyWages));
        if (threshold)
        {
            tree.Add("threshold_hourly_rate", ProximityCoerce.Truthy(floors.MinWeeklyHours)
                ? ProximityCoerce.RoundHalfUp(ProximityCoerce.ToFloat(floors.MinWeeklyWages) / ProximityCoerce.ToFloat(floors.MinWeeklyHours), decimals)
                : null);
        }

        return tree.Add("source", $"rules/{AsciiLower(floors.ProgramCode)}/{floors.TaxYear}.json");
    }

    /// <summary>Python <c>str.lower()</c> for the ASCII program codes the rule packs use; anything else is refused rather than guessed.</summary>
    private static string AsciiLower(string s) =>
        s.All(c => c < 128) ? s.ToLowerInvariant() : throw new PyUnsupportedException("str.lower() of non-ASCII program codes is not modelled");

    private static object? Req(PyDict population, string key) =>
        population.TryGetValue(key, out var v) ? v : throw ProximityCoerce.Missing(key);

    /// <summary>Python <c>dict(x)</c> of a supplied mapping (a copy, same order); <c>None</c> is a <c>TypeError</c>.</summary>
    private static PyDict CopyDict(object? x) => x switch
    {
        PyDict d => d.Aggregate(new PyDict(), (acc, kv) => acc.Set(kv.Key, kv.Value)),
        null => throw new PyTypeError("'NoneType' object is not iterable"),
        _ => throw new PyUnsupportedException("dict() of " + ProximityCoerce.TypeName(x) + " is not modelled"),
    };
}
