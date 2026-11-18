using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Sources.Projection;

namespace TaxCredit.Infrastructure.Sources.Cache;

/// <summary>
/// A sampled, structural estimate of what a held projection costs on the managed heap. It is an estimate: the cache needs a
/// bound it can enforce without measuring the GC, and a row's cost is dominated by its dictionary, which is what is modelled.
/// </summary>
public static class ProjectionSizeEstimator
{
    private const int Samples = 64;
    // PyDict, its List and Dictionary headers, the PayRow and PayrollRow records, and the eleven RowCell structs the engine view holds.
    private const long RowFixedBytes = 240 + 472;
    // One list slot plus one dictionary entry and bucket, with their growth slack.
    private const long EntryBytes = 56;
    private const long BoxedBytes = 24;
    private const long StringHeaderBytes = 26;

    /// <summary>The estimated bytes the projection's rows hold; zero rows cost nothing beyond a small constant.</summary>
    public static long Estimate(PayrollProjection projection)
    {
        ArgumentNullException.ThrowIfNull(projection);
        var rows = projection.Rows;
        if (rows.Count == 0) { return 1024; }
        var step = Math.Max(1, rows.Count / Samples);
        long sampled = 0;
        var taken = 0;
        for (var i = 0; i < rows.Count && taken < Samples; i += step, taken++)
        {
            sampled += RowBytes(rows[i].Dict);
        }
        return 1024 + sampled * rows.Count / taken + rows.Count * 8L;
    }

    private static long RowBytes(PyDict dict)
    {
        var bytes = RowFixedBytes;
        foreach (var pair in dict)
        {
            bytes += EntryBytes + pair.Value switch
            {
                null => 0,
                string text => StringHeaderBytes + 2L * text.Length,
                _ => BoxedBytes,
            };
        }
        return bytes;
    }
}
