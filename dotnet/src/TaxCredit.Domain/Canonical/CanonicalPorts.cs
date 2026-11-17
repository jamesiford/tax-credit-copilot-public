using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Canonical;

/// <summary>Python <c>SourceAdapter</c> protocol: anything that can yield raw rows becomes a source (the engine never changes).</summary>
public interface ISourceAdapter
{
    /// <summary>The raw rows, each a dictionary of loosely typed cells.</summary>
    /// <returns>The rows in source order.</returns>
    IEnumerable<PyDict> Rows();
}

/// <summary>
/// Python <c>RowsAdapter</c>: rows a caller has already loaded, so a screen cannot read its first number from one source and the rest from another.
/// </summary>
/// <param name="Loaded">The rows.</param>
public sealed record RowsAdapter(IReadOnlyList<PyDict> Loaded) : ISourceAdapter
{
    /// <inheritdoc />
    public IEnumerable<PyDict> Rows() => Loaded;
}

/// <summary>
/// The prototype worksite registry (Python <c>data.sites.SITES</c>), injected rather than imported: it is prototype data, not domain.
/// </summary>
/// <remarks>
/// Why <c>object</c> entries: production's registry holds <c>Site</c> dataclass instances, which have no <c>.get</c>, so the lookup in
/// <c>_worksite_join</c> raises <c>AttributeError</c> on the first entry and the broad <c>except</c> swallows it (finding CQ-01). An entry that is
/// not a <see cref="PyDict"/> models exactly that; a dictionary entry models the dict-shaped registry the lookup was written for.
/// </remarks>
public interface IWorksiteRegistry
{
    /// <summary>The registry entries in order.</summary>
    IReadOnlyList<object?> Sites { get; }
}

/// <summary>
/// Python <c>rules_ingestion.load_ingested_config</c>, the agent-INGESTED cited config the wage base is driven by (CALC-11). Web retrieval is out of scope;
/// the default port is <see cref="NoIngestedConfig"/>.
/// </summary>
public interface IIngestedConfigSource
{
    /// <summary>The cited config tree for a program, or <c>null</c> when none was ingested. May throw: the caller falls back to the default classifier.</summary>
    /// <param name="program">The program code.</param>
    /// <returns>The config tree or <c>null</c>.</returns>
    object? Load(string program);
}

/// <summary>The 'none' ingested-config source: nothing is ingested, so the conservative default classifier applies.</summary>
public sealed class NoIngestedConfig : IIngestedConfigSource
{
    /// <inheritdoc />
    public object? Load(string program) => null;
}
