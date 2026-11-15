using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests;

internal sealed class PersistenceFixture : IDisposable
{
    internal string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "tcc-persistence-" + Guid.NewGuid().ToString("N") + ".db");
    internal static string Root { get; } = FindRoot();
    internal PersistenceDatabase Database { get; }

    internal PersistenceFixture(bool initialize = true)
    {
        Database = PersistenceDatabase.Sqlite(Path);
        if (initialize)
        {
            PersistenceSchema.Initialize(Database, Root);
        }
    }

    internal SeedLoadResult Load(string profile) => new SeedImporter(Database, System.IO.Path.Combine(Root, "contract", "seed")).Load(profile);

    private static string FindRoot()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !Directory.Exists(System.IO.Path.Combine(directory.FullName, "contract", "seed")))
        {
            directory = directory.Parent;
        }

        return directory?.FullName ?? throw new DirectoryNotFoundException("Repository root not found.");
    }

    public void Dispose() => File.Delete(Path);
}
