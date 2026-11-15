using System.IO.Compression;
using System.Text.Json;

namespace TaxCredit.Parity.Tests;

/// <summary>Locates and streams the Python-exported golden files under <c>parity/goldens</c>.</summary>
internal static class GoldenFiles
{
    /// <summary>The repository's <c>parity</c> folder, found by walking up from the test binary.</summary>
    public static string ParityDirectory { get; } = Locate();

    /// <summary>Streams every JSON line of a gzip-compressed JSONL golden whose <c>"k"</c> value equals <paramref name="kind"/>.</summary>
    public static IEnumerable<JsonElement> Read(string file, string kind)
    {
        var prefix = "{\"k\":\"" + kind + "\"";
        using var stream = File.OpenRead(Path.Combine(ParityDirectory, "goldens", file));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            if (!line.StartsWith(prefix, StringComparison.Ordinal))
            {
                continue;
            }

            using var doc = JsonDocument.Parse(line);
            yield return doc.RootElement.Clone();
        }
    }

    private static string Locate()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "parity", "export_primitives.py");
            if (File.Exists(candidate))
            {
                return Path.Combine(dir.FullName, "parity");
            }

            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate the repository's parity folder.");
    }
}
