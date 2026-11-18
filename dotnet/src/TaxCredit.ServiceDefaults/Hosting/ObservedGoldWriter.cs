using TaxCredit.Application.Hosting;
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
        using var span = RunSpans.Start("gold.write");
        var marker = source.Fingerprint(payload.ClientId);
        var counts = writer.WriteRun(payload);
        using (RunSpans.Start("persist.observation")) { observations.Record(payload.ClientId, payload.RunId, marker); }
        return counts;
    }

    public IReadOnlyList<(string Query, long RowCount)> Validate() => writer.Validate();
}
