using TaxCredit.Domain.DataMap;
using Map = TaxCredit.Domain.DataMap.DataMap;

namespace TaxCredit.Architecture.Tests;

/// <summary>
/// Physical database names live in the data map and nowhere else. Code speaks logical names (<c>{ops.run_manifest}</c>);
/// one resolver maps them. A literal schema name in source defeats a customer's data map.
/// </summary>
public sealed class DataMapLiteralTests
{
    private static string SourceDirectory()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "TaxCredit.slnx")))
        {
            dir = dir.Parent;
        }

        return Path.Combine(dir?.FullName ?? throw new DirectoryNotFoundException("TaxCredit.slnx not found."), "src");
    }

    [Fact]
    public void No_source_file_spells_a_physical_schema_name_from_the_shipped_map()
    {
        var map = Map.Default;
        var physical = new[] { map.GoldSchema, map.OpsSchema, map.SourceSchema };
        var offenders = Directory.EnumerateFiles(SourceDirectory(), "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar, StringComparison.Ordinal)
                && !f.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            .SelectMany(f => File.ReadLines(f).Select((line, i) => (f, line, n: i + 1)))
            .Where(x => physical.Any(p => x.line.Contains(p + ".", StringComparison.Ordinal) || x.line.Contains('"' + p + '"', StringComparison.Ordinal)
                || x.line.Contains("(" + p + ")", StringComparison.Ordinal)))
            .Select(x => Path.GetRelativePath(SourceDirectory(), x.f) + ":" + x.n)
            .ToList();
        Assert.True(offenders.Count == 0, "Physical schema names must come from the data map: " + string.Join(", ", offenders.Take(10)));
        _ = new PhysicalNames(map);
    }
}
