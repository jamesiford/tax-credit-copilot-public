using System.Data;
using System.Data.Common;
using System.Numerics;
using Microsoft.Data.SqlClient;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>
/// When a SQL Server-family destination streams a large insert through the TDS bulk-load protocol instead of multi-row INSERT statements.
/// The bulk path runs on the caller's connection and transaction, so atomicity is exactly that of the statements it replaces.
/// </summary>
/// <param name="Enabled">False sends every insert as bounded multi-row statements, the behaviour before bulk loading existed.</param>
/// <param name="MinimumRows">Inserts smaller than this keep using statements: a bulk load has a fixed cost that tiny batches never recover.</param>
/// <param name="TimeoutSeconds">Whole-operation timeout for one table's bulk load; zero would mean unlimited and is refused.</param>
public sealed record BulkLoadPolicy(bool Enabled, int MinimumRows, int TimeoutSeconds)
{
    /// <summary>Statement inserts only (SQLite, and the kill switch for a destination that rejects the bulk protocol).</summary>
    public static BulkLoadPolicy Off { get; } = new(false, int.MaxValue, 600);

    /// <summary>The default for SQL Server-family destinations.</summary>
    public static BulkLoadPolicy Default { get; } = new(true, 1000, 3600);

    /// <summary>Reads <c>BULK_LOAD</c> (<c>on</c> or <c>off</c>), <c>BULK_LOAD_MIN_ROWS</c> and <c>BULK_TIMEOUT_SECONDS</c>.</summary>
    public static BulkLoadPolicy FromSettings(Func<string, string?> setting)
    {
        ArgumentNullException.ThrowIfNull(setting);
        var enabled = setting("BULK_LOAD")?.Trim().ToLowerInvariant() switch
        {
            null or "" or "on" or "true" or "1" => true,
            "off" or "false" or "0" => false,
            _ => throw new InvalidOperationException("Invalid setting BULK_LOAD: use on or off."),
        };
        return new BulkLoadPolicy(enabled, Number(setting, "BULK_LOAD_MIN_ROWS", Default.MinimumRows, 1),
            Number(setting, "BULK_TIMEOUT_SECONDS", Default.TimeoutSeconds, 1));
    }

    private static int Number(Func<string, string?> setting, string key, int fallback, int minimum)
    {
        var text = setting(key);
        if (string.IsNullOrWhiteSpace(text))
        {
            return fallback;
        }

        return int.TryParse(text, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var value) && value >= minimum
            ? value
            : throw new InvalidOperationException("Invalid setting " + key + ": a whole number of at least " + minimum + ".");
    }
}

/// <summary>Sends validated rows to one table on the caller's connection; replaceable so the strategy is testable without a server.</summary>
internal interface IBulkWriter
{
    /// <summary>False when the connection or the values cannot be bulk loaded, so the caller keeps its statement path.</summary>
    bool CanWrite(DbConnection connection, IReadOnlyList<IReadOnlyList<object?>> rows);

    /// <summary>Writes every row in order inside <paramref name="transaction"/> (or auto-commit when null) and returns the count.</summary>
    int Write(DbConnection connection, DbTransaction? transaction, string table, IReadOnlyList<string> columns,
        IReadOnlyList<IReadOnlyList<object?>> rows, BulkLoadPolicy policy);
}

internal sealed class SqlBulkCopyWriter : IBulkWriter
{
    public bool CanWrite(DbConnection connection, IReadOnlyList<IReadOnlyList<object?>> rows) =>
        connection is SqlConnection && rows.All(row => row.All(cell => SqlValues.Unwrap(cell) is not PyDecimal number || BulkRows.Representable(number)));

    public int Write(DbConnection connection, DbTransaction? transaction, string table, IReadOnlyList<string> columns,
        IReadOnlyList<IReadOnlyList<object?>> rows, BulkLoadPolicy policy)
    {
        using var bulk = new SqlBulkCopy((SqlConnection)connection, SqlBulkCopyOptions.Default, transaction as SqlTransaction)
        {
            DestinationTableName = table,
            BulkCopyTimeout = policy.TimeoutSeconds,
            // One batch per table: the load already sits inside the publish transaction, and a Warehouse prefers a few large batches.
            BatchSize = 0,
        };
        for (var i = 0; i < columns.Count; i++)
        {
            bulk.ColumnMappings.Add(i, columns[i]);
        }

        using var reader = new BulkRows(columns, rows);
        bulk.WriteToServer(reader);
        return rows.Count;
    }
}

/// <summary>A forward-only reader over already-validated rows, converting each cell exactly as a statement parameter would be.</summary>
internal sealed class BulkRows(IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows) : DbDataReader
{
    private int _row = -1;

    internal static bool Representable(PyDecimal number) =>
        number.Exponent >= -28 && number.Exponent <= 28 && number.Coefficient.Sign >= 0 && Scaled(number) <= MaxCoefficient;

    private static BigInteger Scaled(PyDecimal number) => number.Exponent > 0 ? number.Coefficient * BigInteger.Pow(10, number.Exponent) : number.Coefficient;

    private static readonly BigInteger MaxCoefficient = (BigInteger.One << 96) - 1;

    internal static object Convert(object? value)
    {
        value = SqlValues.Unwrap(value);
        switch (value)
        {
            case null:
                return DBNull.Value;
            case BigInteger integer:
                return checked((long)integer);
            case PyDecimal number:
                var parts = Scaled(number);
                return new decimal((int)(uint)(parts & uint.MaxValue), (int)(uint)((parts >> 32) & uint.MaxValue),
                    (int)(uint)((parts >> 64) & uint.MaxValue), number.Negative, (byte)Math.Max(0, -number.Exponent));
            case DateOnly day:
                return day.ToDateTime(TimeOnly.MinValue);
            case PyDateTime time:
                return SqlValues.ToUtc(time);
            default:
                return value;
        }
    }

    public override int FieldCount => columns.Count;
    public override bool HasRows => rows.Count > 0;
    public override bool IsClosed => false;
    public override int Depth => 0;
    public override int RecordsAffected => -1;
    public override object this[int ordinal] => GetValue(ordinal);
    public override object this[string name] => GetValue(GetOrdinal(name));

    public override bool Read() => ++_row < rows.Count;
    public override bool NextResult() => false;
    public override object GetValue(int ordinal) => Convert(rows[_row][ordinal]);
    public override bool IsDBNull(int ordinal) => SqlValues.Unwrap(rows[_row][ordinal]) is null;
    public override string GetName(int ordinal) => columns[ordinal];
    public override int GetOrdinal(string name) => columns.ToList().IndexOf(name);
    public override Type GetFieldType(int ordinal) => typeof(object);
    public override string GetDataTypeName(int ordinal) => "object";
    public override int GetValues(object[] values)
    {
        for (var i = 0; i < columns.Count; i++)
        {
            values[i] = GetValue(i);
        }

        return columns.Count;
    }

    public override System.Collections.IEnumerator GetEnumerator() => throw new NotSupportedException();
    public override bool GetBoolean(int ordinal) => (bool)GetValue(ordinal);
    public override byte GetByte(int ordinal) => (byte)GetValue(ordinal);
    public override long GetBytes(int ordinal, long dataOffset, byte[]? buffer, int bufferOffset, int length) => throw new NotSupportedException();
    public override char GetChar(int ordinal) => (char)GetValue(ordinal);
    public override long GetChars(int ordinal, long dataOffset, char[]? buffer, int bufferOffset, int length) => throw new NotSupportedException();
    public override DateTime GetDateTime(int ordinal) => (DateTime)GetValue(ordinal);
    public override decimal GetDecimal(int ordinal) => (decimal)GetValue(ordinal);
    public override double GetDouble(int ordinal) => (double)GetValue(ordinal);
    public override float GetFloat(int ordinal) => (float)GetValue(ordinal);
    public override Guid GetGuid(int ordinal) => (Guid)GetValue(ordinal);
    public override short GetInt16(int ordinal) => (short)GetValue(ordinal);
    public override int GetInt32(int ordinal) => (int)GetValue(ordinal);
    public override long GetInt64(int ordinal) => (long)GetValue(ordinal);
    public override string GetString(int ordinal) => (string)GetValue(ordinal);
}
