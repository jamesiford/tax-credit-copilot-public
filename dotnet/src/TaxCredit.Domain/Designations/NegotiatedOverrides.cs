using System.Globalization;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Designations;

/// <summary>
/// Negotiated-incentive wage-standard overrides (Python <c>tools/negotiated.py</c>, CALC-10): terms that come from a contract, not the rule pack.
/// The store starts empty, so <see cref="Resolve"/> returns <c>null</c> and the statutory pack values stand unaltered.
/// </summary>
/// <remarks>
/// Why an instance: Python keeps the store in a module-level dict (<c>_OVERRIDES</c>); a process-wide mutable singleton does not belong in the domain,
/// so the composition root owns one instance and the clock is a seam (<c>datetime.now(timezone.utc)</c>), see findings BY-04.
/// </remarks>
/// <param name="utcNow">The clock: the current UTC instant.</param>
public sealed class NegotiatedOverrides(Func<DateTime> utcNow)
{
    private PyDict _overrides = new();

    /// <summary>Python <c>resolve_override</c>: the override for a state, a worksite-specific one winning over the state-wide one.</summary>
    /// <param name="state">The state code.</param>
    /// <param name="worksite">The worksite id, if any.</param>
    /// <returns>The record, or <c>null</c> when none is on file.</returns>
    public PyDict? Resolve(string state, string? worksite = null)
    {
        ArgumentNullException.ThrowIfNull(state);
        var su = PyStr.Upper(state);
        if (!string.IsNullOrEmpty(worksite) && _overrides.TryGetValue(Key(su, worksite), out var specific))
        {
            return (PyDict?)specific;
        }

        return _overrides.TryGetValue(su, out var general) ? (PyDict?)general : null;
    }

    /// <summary>Python <c>register_override</c>: records a negotiated override (the seam a real agreement store plugs into).</summary>
    /// <param name="state">The state code (stored upper-cased).</param>
    /// <param name="worksiteId">The worksite the override is specific to, if any.</param>
    /// <param name="wageStandardWeekly">The negotiated weekly wage standard (int or float, kept as given).</param>
    /// <param name="minJobs">The negotiated minimum jobs (int or float, kept as given).</param>
    /// <param name="source"><c>self_service</c> or <c>agreement</c>.</param>
    /// <param name="effectiveYears">How many years it applies, if stated.</param>
    /// <param name="note">A free-text note.</param>
    /// <returns>The stored record.</returns>
    /// <exception cref="PyValueError">When neither value is given or the source is unknown.</exception>
    public PyDict Register(
        string state,
        string? worksiteId = null,
        PyNumber? wageStandardWeekly = null,
        PyNumber? minJobs = null,
        string source = "self_service",
        long? effectiveYears = null,
        string? note = null)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (wageStandardWeekly is null && minJobs is null)
        {
            throw new PyValueError("provide wage_standard_weekly and/or min_jobs");
        }

        if (source is not ("self_service" or "agreement"))
        {
            throw new PyValueError("source must be self_service or agreement");
        }

        var record = new PyDict()
            .Add("_roadmap_tag", "L4").Add("_story", "CALC-10").Add("_disc_ref", "DISC-13")
            .Add("state", PyStr.Upper(state)).Add("worksite_id", worksiteId)
            .Add("wage_standard_weekly", PyNum.Tree(wageStandardWeekly)).Add("min_jobs", PyNum.Tree(minJobs))
            .Add("source", source).Add("effective_years", effectiveYears).Add("note", note)
            .Add("updated_at", utcNow().ToString("yyyy-MM-dd'T'HH:mm:ss'+00:00'", CultureInfo.InvariantCulture));
        _overrides.Set(Key(state, worksiteId), record);
        return record;
    }

    /// <summary>Python <c>list_overrides</c>: a shallow copy of the store, keyed by state or <c>state:worksite</c>.</summary>
    /// <returns>The copy.</returns>
    public PyDict List() => _overrides.Aggregate(new PyDict(), (d, kv) => d.Set(kv.Key, kv.Value));

    /// <summary>Python <c>_reset_for_tests</c>: clears the store.</summary>
    public void Reset() => _overrides = new PyDict();

    /// <summary>Python <c>_key</c>: <c>STATE:WORKSITE</c> for a non-empty worksite, else <c>STATE</c>.</summary>
    private static string Key(string state, string? worksite) =>
        string.IsNullOrEmpty(worksite) ? PyStr.Upper(state) : $"{PyStr.Upper(state)}:{worksite}";
}
