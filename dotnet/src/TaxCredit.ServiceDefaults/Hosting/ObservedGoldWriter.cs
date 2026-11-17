using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence;

namespace TaxCredit.ServiceDefaults.Hosting;

internal sealed class ObservedGoldWriter(GoldWriter writer, ISourceFingerprintReader source,
    IRunSourceObservations observations) : IGoldWriter
{
    public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload)
    {
        var marker = source.Fingerprint(payload.ClientId);
        var counts = writer.WriteRun(payload);
        observations.Record(payload.ClientId, payload.RunId, marker);
        return counts;
    }

    public IReadOnlyList<(string Query, long RowCount)> Validate() => writer.Validate();
}
