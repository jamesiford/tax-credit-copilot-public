namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Hermetic source-shaped rows for the Sources adapter; no source projection happens in persistence.</summary>
public interface ISeedData
{
    /// <summary>The source tables staged by the last successful reset, with declared column names.</summary>
    IReadOnlyDictionary<string, IReadOnlyList<string>> Tables();

    /// <summary>Streams one whitelisted source table in seed order as its original JSON object.</summary>
    IEnumerable<string> ReadTable(string table);
}
