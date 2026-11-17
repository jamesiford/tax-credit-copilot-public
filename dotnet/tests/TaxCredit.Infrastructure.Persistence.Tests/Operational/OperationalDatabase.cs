using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

internal sealed class OperationalDatabase : IDisposable
{
    private readonly string _folder;
    internal OperationalDatabase()
    {
        _folder = System.IO.Path.Combine(Environment.CurrentDirectory, "operational-test-data", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_folder);
        Path = System.IO.Path.Combine(_folder, "operations.db");
        Database = PersistenceDatabase.Sqlite(Path, Messages.Add);
        try
        {
            PersistenceSchema.Initialize(Database, Root());
            Infrastructure.Persistence.Operational.OperationalSchema.Initialize(Database);
        }
        catch
        {
            Directory.Delete(_folder, recursive: true);
            throw;
        }
    }

    internal string Path { get; }
    internal PersistenceDatabase Database { get; }
    internal List<string> Messages { get; } = [];
    internal PersistenceDatabase Reopen() => PersistenceDatabase.Sqlite(Path, Messages.Add);

    internal static string Root()
    {
        var directory = new DirectoryInfo(Environment.CurrentDirectory);
        while (directory is not null && !File.Exists(System.IO.Path.Combine(directory.FullName, "docs", "data", "schema", "tcc-schema.sqlserver.sql")))
        {
            directory = directory.Parent;
        }

        return directory?.FullName ?? throw new DirectoryNotFoundException("The checked-in schema is required.");
    }

    public void Dispose()
    {
        Directory.Delete(_folder, recursive: true);
    }
}
