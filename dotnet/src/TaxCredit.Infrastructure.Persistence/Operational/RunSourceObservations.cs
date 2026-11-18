using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Count/max evidence is not substituted for the certified content hash or claimed as a historical snapshot.</summary>
public sealed class RunSourceObservations(PersistenceDatabase database) : IRunSourceObservations
{
    /// <inheritdoc />
    public void Record(long clientId, string runId, SourceFingerprint fingerprint) => database.Transact(session =>
        session.Insert(clientId, "ops.run_source_observation", ["client_id", "run_id", "observation_json"],
            [[clientId, runId, JsonSerializer.Serialize(fingerprint)]]));

    /// <inheritdoc />
    public SourceFingerprint? Get(long clientId, string runId)
    {
        using var session = database.Open();
        var rows = session.Query(clientId, "SELECT observation_json FROM {ops.run_source_observation} WHERE {tenant} AND run_id = ?", runId);
        return rows.Count == 0 ? null : JsonSerializer.Deserialize<SourceFingerprint>((string)rows.Single()["observation_json"]!)
            ?? throw new InvalidDataException("A stored source observation is invalid.");
    }
}
