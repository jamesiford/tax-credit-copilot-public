using System.IO.Compression;
using System.Text;
using System.Text.Json;

namespace TaxCredit.Infrastructure.Ai.Safety;

/// <summary>Invariant-globalization disables BCL normalization, so screening uses CPython 3.12 Unicode 15 scalar folds.</summary>
internal static class UnicodeFold
{
    private static readonly Dictionary<int, string> Folds = Read();
    public static string Normalize(string text)
    {
        var output = new StringBuilder(text.Length);
        foreach (var rune in text.EnumerateRunes())
        {
            output.Append(Folds.TryGetValue(rune.Value, out string? folded) ? folded : rune.ToString());
        }
        return output.ToString().Normalize(NormalizationForm.FormKC);
    }
    private static Dictionary<int, string> Read()
    {
        using var resource = typeof(UnicodeFold).Assembly.GetManifestResourceStream("TaxCredit.Ai.UnicodeFold")
            ?? throw new InvalidOperationException("Missing Unicode screening resource.");
        using var gzip = new GZipStream(resource, CompressionMode.Decompress);
        using var doc = JsonDocument.Parse(gzip);
        return doc.RootElement.EnumerateObject().ToDictionary(
            p => int.Parse(p.Name, System.Globalization.CultureInfo.InvariantCulture), p => p.Value.GetString()!);
    }
}
