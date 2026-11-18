using System.Security.Cryptography;
using System.Text;
using Microsoft.Data.Sqlite;

namespace TaxCredit.Api.Tests.Bench;

/// <summary>
/// A content hash of every stored Gold row. The run id and timestamp columns are the only columns left out: a run id is a fresh identity
/// per run and a timestamp is the clock, neither is a calculated figure. Rows are ordered by their own text so storage order cannot matter.
/// </summary>
internal static class GoldDump
{
    internal static string Hash(string databasePath, string? dumpPath = null)
    {
        using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = databasePath, Mode = SqliteOpenMode.ReadOnly, Pooling = false }.ConnectionString);
        connection.Open();
        var tables = Query(connection, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tcc_gold%' ORDER BY name")
            .Select(r => (string)r[0]!).ToArray();
        var summary = new StringBuilder();
        using var all = SHA256.Create();
        StreamWriter? file = dumpPath is null ? null : new StreamWriter(dumpPath);
        foreach (var table in tables)
        {
            var columns = Query(connection, $"PRAGMA table_info(\"{table}\")").Select(r => (string)r[1]!)
                .Where(c => c != "run_id" && !c.EndsWith("_at", StringComparison.Ordinal)).ToArray();
            var lines = Query(connection, $"SELECT {string.Join(",", columns.Select(c => "\"" + c + "\""))} FROM \"{table}\"")
                .Select(r => string.Join("\u001f", r.Select(v => v is null ? "\u0000NULL" : Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture))))
                .Order(StringComparer.Ordinal).ToArray();
            using var one = SHA256.Create();
            foreach (var line in lines)
            {
                one.TransformBlock(Encoding.UTF8.GetBytes(line + "\n"), 0, Encoding.UTF8.GetByteCount(line) + 1, null, 0);
                file?.WriteLine(table + "\t" + line);
            }
            one.TransformFinalBlock([], 0, 0);
            var hash = Convert.ToHexStringLower(one.Hash!);
            summary.Append(table).Append(' ').Append(lines.Length).Append(' ').AppendLine(hash[..16]);
            var bytes = Encoding.UTF8.GetBytes(table + hash);
            all.TransformBlock(bytes, 0, bytes.Length, null, 0);
        }
        file?.Dispose();
        all.TransformFinalBlock([], 0, 0);
        return Convert.ToHexStringLower(all.Hash!) + "\n" + summary;
    }

    private static List<object?[]> Query(SqliteConnection connection, string sql)
    {
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        using var reader = command.ExecuteReader();
        var rows = new List<object?[]>();
        while (reader.Read())
        {
            var row = new object?[reader.FieldCount];
            for (var i = 0; i < row.Length; i++) { row[i] = reader.IsDBNull(i) ? null : reader.GetValue(i); }
            rows.Add(row);
        }
        return rows;
    }
}
