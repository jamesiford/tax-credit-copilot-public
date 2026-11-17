using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Simulation;

/// <summary>A resolved what-if location: the state code and, for a known city, its county.</summary>
/// <param name="State">The two-letter state (upper case for a typed code, as Python <c>key.upper()</c>).</param>
/// <param name="County">The county, <c>null</c> for a bare state code.</param>
public sealed record ResolvedLocation(string State, string? County);

/// <summary>Python <c>tools/simulation.py</c> <c>_CITY_MAP</c> and <c>_resolve_location</c>: the demo's coarse city to (state, county) lookup.</summary>
public static class LocationResolver
{
    /// <summary>Python <c>_CITY_MAP</c>, in source order.</summary>
    public static IReadOnlyDictionary<string, ResolvedLocation> CityMap { get; } = new Dictionary<string, ResolvedLocation>(StringComparer.Ordinal)
    {
        ["atlanta"] = new("GA", "Fulton"),
        ["savannah"] = new("GA", "Chatham"),
        ["macon"] = new("GA", "Bibb"),
        ["new york"] = new("NY", "New York"),
        ["brooklyn"] = new("NY", "Kings"),
        ["charleston"] = new("SC", "Charleston"),
        ["greenville"] = new("SC", "Greenville"),
        ["austin"] = new("TX", "Travis"),
        ["houston"] = new("TX", "Harris"),
        ["dallas"] = new("TX", "Dallas"),
        ["charlotte"] = new("NC", "Mecklenburg"),
        ["raleigh"] = new("NC", "Wake"),
        ["nashville"] = new("TN", "Davidson"),
        ["memphis"] = new("TN", "Shelby"),
        ["jacksonville"] = new("FL", "Duval"),
        ["miami"] = new("FL", "Miami-Dade"),
        ["orlando"] = new("FL", "Orange"),
        ["columbus"] = new("OH", "Franklin"),
        ["cincinnati"] = new("OH", "Hamilton"),
        ["cleveland"] = new("OH", "Cuyahoga"),
        ["denver"] = new("CO", "Denver"),
        ["boulder"] = new("CO", "Boulder"),
        ["tysons"] = new("VA", "Fairfax"),
        ["tysons corner"] = new("VA", "Fairfax"),
        ["richmond"] = new("VA", "Richmond"),
        ["arlington"] = new("VA", "Arlington"),
    };

    /// <summary>
    /// Python <c>_resolve_location</c>: a known city gives its state and county; any other two-character text is taken as a state code
    /// (upper-cased, no county); everything else falls back to the demo default, Georgia / Fulton.
    /// </summary>
    /// <param name="cityOrState">The text, or <c>null</c> (Python <c>None or ""</c>).</param>
    /// <returns>The state and county.</returns>
    public static ResolvedLocation Resolve(string? cityOrState)
    {
        // `(x or "").strip().lower()`: lower() is full Unicode lower-casing, so "\u0130" becomes two code points and is no longer 1 long.
        var key = PyStrCase.Lower(PyStr.Strip(cityOrState ?? string.Empty));
        if (CityMap.TryGetValue(key, out var known))
        {
            return known;
        }

        return PyStr.Length(key) == 2 ? new ResolvedLocation(PyStr.Upper(key), null) : new ResolvedLocation("GA", "Fulton");
    }
}
