using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Designations;

/// <summary>One source-schema registry entry: a unit's designation timeline, keyed by client AND unit (source unit ids repeat across clients).</summary>
/// <param name="ClientId">The client.</param>
/// <param name="UnitId">The unit.</param>
/// <param name="History">The timeline, oldest first (<c>{year, tier, designation, min_new_jobs}</c> dictionaries).</param>
public sealed record SourceDesignation(long ClientId, string UnitId, IReadOnlyList<PyDict> History);

/// <summary>
/// The designation registry the Python <c>data/designations.py</c> module holds (prototype data, DISC-10), injected as data: the legacy worksite
/// timelines, the source-schema timelines, the synthetic default, and whether the environment is classified synthetic.
/// </summary>
/// <remarks>Why injected: the domain reads no files and no environment; <c>config.synthetic_environment()</c> is a delegate here and is consulted only when Python would call it.</remarks>
public sealed partial class DesignationRegistry
{
    /// <summary>Python <c>_DISC_REF</c> of the designation module.</summary>
    public const string DiscRef = "DISC-10";

    private readonly IReadOnlyList<KeyValuePair<string, IReadOnlyList<PyDict>>> _legacy;
    private readonly Dictionary<string, IReadOnlyList<PyDict>> _legacyByUnit;
    private readonly Dictionary<(long Client, string Unit), IReadOnlyList<PyDict>> _source;
    private readonly IReadOnlyList<PyDict> _syntheticDefault;
    private readonly Func<bool> _synthetic;

    /// <summary>Creates a registry.</summary>
    /// <param name="legacy">Python <c>_DESIGNATION_HISTORY</c>, in insertion order.</param>
    /// <param name="source">Python <c>_SOURCE_DESIGNATIONS</c>.</param>
    /// <param name="syntheticGaDefault">Python <c>_SYNTHETIC_GA_DEFAULT</c>.</param>
    /// <param name="syntheticEnvironment">Python <c>config.synthetic_environment</c>.</param>
    public DesignationRegistry(
        IReadOnlyList<KeyValuePair<string, IReadOnlyList<PyDict>>> legacy,
        IReadOnlyList<SourceDesignation> source,
        IReadOnlyList<PyDict> syntheticGaDefault,
        Func<bool> syntheticEnvironment)
    {
        ArgumentNullException.ThrowIfNull(legacy);
        ArgumentNullException.ThrowIfNull(source);
        _legacy = legacy;
        _legacyByUnit = legacy.ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.Ordinal);
        _source = source.ToDictionary(s => (s.ClientId, s.UnitId), s => s.History);
        _syntheticDefault = syntheticGaDefault;
        _synthetic = syntheticEnvironment;
    }

    /// <summary>Python <c>disc_meta()</c>.</summary>
    /// <returns>The prototype flag and discussion reference.</returns>
    public static PyDict DiscMeta() => new PyDict().Add("_prototype_verify", true).Add("_disc_ref", DiscRef);

    /// <summary>Python <c>designation_history</c>: the timeline for a location, oldest first.</summary>
    /// <param name="worksiteId">The unit.</param>
    /// <param name="clientId">With a client the source registry is read, keyed by client AND unit; without, the legacy worksite registry.</param>
    /// <returns>Copies of the entries (empty when unassigned).</returns>
    public IReadOnlyList<PyDict> History(string worksiteId, long? clientId = null)
    {
        ArgumentNullException.ThrowIfNull(worksiteId);
        if (clientId is not { } client)
        {
            return _legacyByUnit.TryGetValue(worksiteId, out var legacy) ? legacy.ToList() : [];
        }

        if (_source.TryGetValue((client, worksiteId), out var own))
        {
            return own.Select(Copy).ToList();
        }

        // A real client's designation is a fact we do not hold: unassigned is the honest answer, a guessed tier would move its minimum.
        return _synthetic() && worksiteId.StartsWith("GA_", StringComparison.Ordinal) ? _syntheticDefault.Select(Copy).ToList() : [];
    }

    /// <summary>Python <c>all_designations()</c>: every legacy timeline as a dictionary of list copies.</summary>
    /// <returns>The mapping, in registry order.</returns>
    public PyDict All() => _legacy.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value.Select(e => (object?)e).ToList()));

    /// <summary>Python <c>_designation_at</c> (<c>get_unit_trend.py</c>): the designation in force for a unit in a year, or <c>null</c> when unregistered.</summary>
    /// <param name="unitId">The unit.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="clientId">The client, for a source-schema unit.</param>
    /// <returns>A copy of the latest entry whose year is not after <paramref name="taxYear"/>.</returns>
    public PyDict? DesignationAt(string unitId, long taxYear, long? clientId = null)
    {
        var history = History(unitId, clientId).Where(d => YearOf(d) <= taxYear).ToList();
        return history.Count > 0 ? Copy(history[^1]) : null;
    }

    internal static BigInteger YearOf(PyDict entry) => entry["year"] switch
    {
        long l => l,
        BigInteger b => b,
        bool b => b ? 1 : 0,
        double d => PyArith.Truncate(d),
        var v => throw new PyUnsupportedException("a designation year of type " + (v?.GetType().Name ?? "None") + " is not modelled"),
    };

    internal static PyDict Copy(PyDict source) => source.Aggregate(new PyDict(), (d, kv) => d.Set(kv.Key, kv.Value));
}
