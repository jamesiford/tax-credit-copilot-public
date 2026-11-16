using System.Globalization;
using System.Text.Json;
using TaxCredit.Infrastructure.Persistence.GoldRead;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldFixture : IDisposable
{
    private readonly string _folder;

    public GoldFixture() : this("P1")
    {
    }

    internal GoldFixture(string profile)
    {
        var directory = new DirectoryInfo(Directory.GetCurrentDirectory());
        while (directory is not null && !Directory.Exists(Path.Combine(directory.FullName, "contract", "seed")))
        {
            directory = directory.Parent;
        }
        Root = directory?.FullName ?? throw new InvalidOperationException("Repository root was not found.");
        _folder = Path.Combine(Root, ".gold-read-tests-" + Guid.NewGuid().ToString("N", CultureInfo.InvariantCulture));
        Directory.CreateDirectory(_folder);
        Database = PersistenceDatabase.Sqlite(Path.Combine(_folder, "gold.sqlite"));
        try
        {
            Load = new SeedImporter(Database, Path.Combine(Root, "contract", "seed")).Load(profile);
            Reader = new GoldReader(Database, new FrozenTime());
        }
        catch
        {
            Directory.Delete(_folder, true);
            throw;
        }
    }

    public string Root { get; }
    public PersistenceDatabase Database { get; }
    public SeedLoadResult Load { get; }
    public GoldReader Reader { get; }

    public JsonElement Recording(string name, string id)
    {
        foreach (var line in File.ReadLines(Path.Combine(Root, "contract", "recordings", name + ".jsonl")))
        {
            using var document = JsonDocument.Parse(line);
            if (document.RootElement.GetProperty("id").GetString() == id)
            {
                return document.RootElement.Clone();
            }
        }
        throw new InvalidOperationException("Unknown recorded case: " + id);
    }

    public void Dispose() => Directory.Delete(_folder, true);

    private sealed class FrozenTime : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => new(2026, 1, 15, 12, 0, 0, TimeSpan.Zero);
    }
}

internal static class GoldAssert
{
    internal static JsonElement Json(object? value) => JsonSerializer.SerializeToElement(value);
    internal static void Same(JsonElement expected, object? actual) => SameJson(expected, Json(actual));

    private static void SameJson(JsonElement expected, JsonElement actual)
    {
        Assert.Equal(expected.ValueKind, actual.ValueKind);
        switch (expected.ValueKind)
        {
            case JsonValueKind.Object:
                Assert.Equal(expected.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal),
                    actual.EnumerateObject().Select(p => p.Name).Order(StringComparer.Ordinal));
                foreach (var property in expected.EnumerateObject())
                {
                    SameJson(property.Value, actual.GetProperty(property.Name));
                }
                break;
            case JsonValueKind.Array:
                Assert.Equal(expected.GetArrayLength(), actual.GetArrayLength());
                foreach (var pair in expected.EnumerateArray().Zip(actual.EnumerateArray()))
                {
                    SameJson(pair.First, pair.Second);
                }
                break;
            case JsonValueKind.Number:
                Assert.Equal(expected.GetDouble(), actual.GetDouble());
                break;
            case JsonValueKind.String:
                Assert.Equal(expected.GetString(), actual.GetString());
                break;
            case JsonValueKind.True:
            case JsonValueKind.False:
                Assert.Equal(expected.GetBoolean(), actual.GetBoolean());
                break;
        }
    }

    internal static IReadOnlyList<IReadOnlyDictionary<string, object?>> Rows(IReadOnlyDictionary<string, object?> result, string key) =>
        Assert.IsAssignableFrom<IReadOnlyList<IReadOnlyDictionary<string, object?>>>(result[key]);
    internal static IReadOnlyDictionary<string, object?> Row(IReadOnlyDictionary<string, object?> result, string key) =>
        Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(result[key]);
}
