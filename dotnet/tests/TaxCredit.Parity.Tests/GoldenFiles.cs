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
        AssertOracleStamp(file);
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

    /// <summary>Fails unless the golden's meta line says it was produced by CPython 3.12 without the exploratory override.</summary>
    public static void AssertOracleStamp(string file)
    {
        if (!Checked.Add(file))
        {
            return;
        }

        using var stream = File.OpenRead(Path.Combine(ParityDirectory, "goldens", file));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        using var meta = JsonDocument.Parse(reader.ReadLine() ?? throw new InvalidDataException(file + " is empty"));
        var root = meta.RootElement;
        var version = root.TryGetProperty("python", out var p) ? p.GetString() ?? "" : "";
        if (root.GetProperty("k").GetString() != "meta" || !OracleInterpreter.IsCPython312(version) || root.TryGetProperty("allow_other_python", out _))
        {
            throw new InvalidDataException($"{file} was not produced by the pinned oracle (meta python={version}). " + OracleInterpreter.HowToCreate);
        }
    }

    private static readonly HashSet<string> Checked = [];

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
