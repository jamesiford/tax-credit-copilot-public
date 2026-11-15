using Microsoft.Data.SqlClient;

namespace PlatformSpike;

internal static class Cleanup
{
    internal static async Task Run(SqlConnection connection, ScratchGuard guard)
    {
        const string list = "SELECT o.name, o.type FROM sys.objects o JOIN sys.schemas s ON o.schema_id = s.schema_id WHERE s.name = @schema";
        guard.Check(list);
        await using var find = new SqlCommand(list, connection) { CommandTimeout = 90 };
        find.Parameters.AddWithValue("@schema", ScratchGuard.Schema);
        var tables = new List<string>();
        await using (var reader = await find.ExecuteReaderAsync())
        {
            while (await reader.ReadAsync())
            {
                if (reader.GetString(1).Trim() != "U")
                    throw new InvalidOperationException("Cleanup found a non-table scratch object; operator cleanup required.");
                tables.Add(reader.GetString(0));
            }
        }
        foreach (var table in tables)
            await Execute($"DROP TABLE [{ScratchGuard.Schema}].[{table.Replace("]", "]]", StringComparison.Ordinal)}]");
        const string schemaSql = "SELECT COUNT(*) FROM sys.schemas WHERE name = @schema";
        guard.Check(schemaSql);
        await using var schemas = new SqlCommand(schemaSql, connection) { CommandTimeout = 90 };
        schemas.Parameters.AddWithValue("@schema", ScratchGuard.Schema);
        var schemaCount = Convert.ToInt32(await schemas.ExecuteScalarAsync(), System.Globalization.CultureInfo.InvariantCulture);
        if (schemaCount != 0)
            await Execute($"DROP SCHEMA [{ScratchGuard.Schema}]");
        await using var proof = new SqlCommand(list, connection) { CommandTimeout = 90 };
        proof.Parameters.AddWithValue("@schema", ScratchGuard.Schema);
        guard.Check(list);
        await using var remaining = await proof.ExecuteReaderAsync();
        if (await remaining.ReadAsync()) throw new InvalidOperationException("Cleanup proof failed.");
        Console.WriteLine($"Cleanup proven: {tables.Count} scratch tables dropped; {schemaCount} scratch schemas dropped; zero scratch objects remain.");

        async Task Execute(string sql)
        {
            guard.Check(sql);
            await using var drop = new SqlCommand(sql, connection) { CommandTimeout = 90 };
            await drop.ExecuteNonQueryAsync();
        }
    }
}
