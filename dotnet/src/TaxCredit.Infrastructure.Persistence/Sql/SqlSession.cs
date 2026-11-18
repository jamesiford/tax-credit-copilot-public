using System.Data;
using System.Data.Common;
using System.Globalization;
using TaxCredit.Application.Hosting;

namespace TaxCredit.Infrastructure.Persistence.Sql;

internal enum SqlExemption
{
    Portfolio,
    Worker,
    Validation,
    Schema,
    Seed,
    ManifestIdentity,
    ChannelIdentity,
    OperationalSequence,
}

/// <summary>Owned connection scope: ordinary repository operations always require a tenant.</summary>
public sealed class SqlSession : IDisposable
{
    private readonly DbConnection _connection;
    private readonly IReadOnlyList<string> _sourceColumns;
    private readonly Action<string> _log;
    private DbTransaction? _transaction;
    private readonly bool _ownsConnection = true;

    internal SqlSession(DbConnection connection, ISqlDialect dialect, IReadOnlyList<string> sourceColumns, Action<string> log)
    {
        _connection = connection;
        Dialect = dialect;
        _sourceColumns = sourceColumns;
        _log = log;
    }

    private SqlSession(SqlSession source)
    {
        _connection = source._connection;
        _transaction = source._transaction;
        _sourceColumns = source._sourceColumns;
        _log = source._log;
        Dialect = source.Dialect;
        _ownsConnection = false;
    }

    internal SqlSession Borrow() => new(this);

    /// <summary>The destination's provider syntax.</summary>
    public ISqlDialect Dialect { get; }

    /// <summary>Executes a tenant-bound read with explicit adapter projections.</summary>
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Query(long clientId, string sql, params object?[] values) =>
        Read(new TenantBinding(clientId, _sourceColumns).Bind(sql, values));

    /// <summary>Bounds governed reads without returning an incomplete collection as success.</summary>
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> QueryBounded(
        long clientId, string sql, int maximumRows, int timeoutSeconds, CancellationToken cancellationToken, params object?[] values)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(maximumRows, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(maximumRows, 10001);
        ArgumentOutOfRangeException.ThrowIfLessThan(timeoutSeconds, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(timeoutSeconds, 600);
        cancellationToken.ThrowIfCancellationRequested();
        using var command = Command(new TenantBinding(clientId, _sourceColumns).Bind(sql, values));
        command.CommandTimeout = timeoutSeconds;
        return BoundedRead.Read(_connection, command, maximumRows, timeoutSeconds, _log, cancellationToken);
    }

    /// <summary>Executes a tenant-bound mutation.</summary>
    public int Execute(long clientId, string sql, params object?[] values) =>
        Run(new TenantBinding(clientId, _sourceColumns).Bind(sql, values));

    /// <summary>Validates all rows first and sends bounded multi-row parameterized batches.</summary>
    public int Insert(long clientId, string table, IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        new TenantBinding(clientId, _sourceColumns).CheckInsert(columns, rows);
        return InsertRows(table, columns, rows);
    }

    internal int InsertExempt(SqlExemption exemption, string table, IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        LogExemption(exemption);
        return InsertRows(table, columns, rows);
    }

    internal IReadOnlyList<IReadOnlyDictionary<string, object?>> QueryExempt(SqlExemption exemption, string sql, params object?[] values)
    {
        LogExemption(exemption);
        return Read(new BoundStatement(sql, values));
    }

    internal int ExecuteExempt(SqlExemption exemption, string sql, params object?[] values)
    {
        LogExemption(exemption);
        return Run(new BoundStatement(sql, values));
    }

    internal IEnumerable<string> StreamStringsExempt(SqlExemption exemption, string sql, params object?[] values)
    {
        LogExemption(exemption);
        using var command = Command(new BoundStatement(sql, values));
        using var reader = command.ExecuteReader(CommandBehavior.SequentialAccess);
        while (reader.Read())
        {
            yield return reader.GetString(0);
        }
    }

    internal void Begin(bool deferWriteLock = false)
    {
        using var span = RunSpans.Start("db.begin");
        _transaction = _connection.BeginTransaction(deferWriteLock && Dialect is SqliteDialect ? IsolationLevel.ReadCommitted : IsolationLevel.Serializable);
    }

    internal void Commit()
    {
        using var span = RunSpans.Start("db.commit");
        _transaction!.Commit();
    }

    internal void Rollback() => _transaction?.Rollback();

    private void LogExemption(SqlExemption exemption)
    {
        if (!Enum.IsDefined(exemption))
        {
            throw new TenantScopeViolation("A tenant exemption requires a named reason.");
        }

        _log("tenant-exempt SQL: " + (exemption switch
        {
            SqlExemption.Portfolio => "portfolio coverage intentionally spans requested clients",
            SqlExemption.Worker => "worker claims/reaps the global queue",
            SqlExemption.Validation => "section-9 invariants span the store",
            SqlExemption.Schema => "configured schema administration",
            SqlExemption.Seed => "transactional reset of verified hermetic seeds",
            SqlExemption.ManifestIdentity => "manifest lookup by globally unique run identity",
            SqlExemption.ChannelIdentity => "global channel or draft identity storage",
            SqlExemption.OperationalSequence => "transactional global append sequence; payload writes remain tenant-bound",
            _ => throw new TenantScopeViolation("Unknown exemption."),
        }));
    }

    private int InsertRows(string table, IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        if (columns.Count == 0 || columns.Count > 2090 || columns.Any(c => !TenantBinding.Identifier().IsMatch(c)))
        {
            throw new TenantScopeViolation("Invalid insert columns.");
        }

        var name = Dialect.Name(table);
        if (Dialect is SqliteDialect)
        {
            return InsertPrepared(name, table, columns, rows);
        }

        if (Dialect is SqlServerDialect { Bulk: { Enabled: true } policy } server && rows.Count >= policy.MinimumRows
            && server.Writer.CanWrite(_connection, rows))
        {
            return BulkInsert(server.Writer, policy, table, name, columns, rows);
        }

        var size = Math.Min(500, 2090 / columns.Count);
        var count = 0;
        for (var start = 0; start < rows.Count; start += size)
        {
            RunLeaseScope.ThrowIfLost();
            var batch = rows.Skip(start).Take(size).ToArray();
            if (batch.Any(r => r.Count != columns.Count))
            {
                throw new TenantScopeViolation("Insert column/value count mismatch.");
            }

            var tuple = "(" + string.Join(",", columns.Select(_ => "?")) + ")";
            var sql = "INSERT INTO " + name + " (" + string.Join(",", columns) + ") VALUES "
                + string.Join(",", batch.Select(_ => tuple));
            using var statement = RunSpans.Start("sql.insert-batch");
            if (statement is not null)
            {
                statement.SetTag("table", table);
                statement.SetTag("rows", batch.Length);
                statement.SetTag("bytes", sql.Length);
                statement.SetTag("parameters", batch.Length * columns.Count);
            }

            count += Run(new BoundStatement(sql, batch.SelectMany(r => r).ToArray()));
        }

        return count;
    }

    private int BulkInsert(IBulkWriter writer, BulkLoadPolicy policy, string table, string name, IReadOnlyList<string> columns,
        IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        if (rows.Any(r => r.Count != columns.Count))
        {
            throw new TenantScopeViolation("Insert column/value count mismatch.");
        }

        using var span = RunSpans.Start("sql.bulk-copy");
        if (span is not null)
        {
            span.SetTag("table", table);
            span.SetTag("rows", rows.Count);
            span.SetTag("parameters", columns.Count);
        }

        return writer.Write(_connection, _transaction, name, columns, rows, policy);
    }

    // Microsoft.Data.Sqlite resolves a named parameter by a linear scan of the collection, so one statement carrying thousands of
    // parameters costs quadratic time (about 20 ms for 2,090). A single-row statement is prepared once and re-bound per row instead:
    // same rows, same order, same transaction.
    private int InsertPrepared(string name, string table, IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        if (rows.Any(r => r.Count != columns.Count))
        {
            throw new TenantScopeViolation("Insert column/value count mismatch.");
        }

        if (rows.Count == 0)
        {
            return 0;
        }

        var sql = "INSERT INTO " + name + " (" + string.Join(",", columns) + ") VALUES ("
            + string.Join(",", columns.Select((_, i) => "@p" + i.ToString(CultureInfo.InvariantCulture))) + ")";
        using var statement = RunSpans.Start("sql.insert-batch");
        if (statement is not null)
        {
            statement.SetTag("table", table);
            statement.SetTag("rows", rows.Count);
            statement.SetTag("bytes", sql.Length);
            statement.SetTag("parameters", columns.Count);
        }

        using var command = _connection.CreateCommand();
        command.CommandText = sql;
        command.Transaction = _transaction;
        command.CommandTimeout = 600;
        var parameters = new DbParameter[columns.Count];
        for (var i = 0; i < parameters.Length; i++)
        {
            parameters[i] = command.CreateParameter();
            parameters[i].ParameterName = "@p" + i.ToString(CultureInfo.InvariantCulture);
            command.Parameters.Add(parameters[i]);
        }

        var count = 0;
        foreach (var row in rows)
        {
            for (var i = 0; i < parameters.Length; i++)
            {
                parameters[i].ResetDbType();
                SqlValues.Bind(parameters[i], row[i], true);
            }

            count += command.ExecuteNonQuery();
        }

        return count;
    }

    private DbCommand Command(BoundStatement statement)
    {
        statement = SqlLex.NameParameters(statement);
        var command = _connection.CreateCommand();
        try
        {
            command.CommandText = Dialect.Translate(statement.Sql);
            command.Transaction = _transaction;
            command.CommandTimeout = 600;
            for (var i = 0; i < statement.Values.Count; i++)
            {
                var parameter = command.CreateParameter();
                parameter.ParameterName = "@p" + i.ToString(CultureInfo.InvariantCulture);
                SqlValues.Bind(parameter, statement.Values[i], Dialect is SqliteDialect);
                command.Parameters.Add(parameter);
            }

            return command;
        }
        catch
        {
            command.Dispose();
            throw;
        }
    }

    private int Run(BoundStatement statement)
    {
        using var span = RunSpans.Start("sql.execute");
        using var command = Command(statement);
        return command.ExecuteNonQuery();
    }

    private List<IReadOnlyDictionary<string, object?>> Read(BoundStatement statement)
    {
        using var span = RunSpans.Start("sql.query");
        using var command = Command(statement);
        using var reader = command.ExecuteReader();
        var rows = new List<IReadOnlyDictionary<string, object?>>();
        while (reader.Read())
        {
            var row = new Dictionary<string, object?>(StringComparer.Ordinal);
            for (var i = 0; i < reader.FieldCount; i++)
            {
                row.Add(reader.GetName(i), reader.IsDBNull(i) ? null : reader.GetValue(i));
            }

            rows.Add(row);
        }

        return rows;
    }

    /// <summary>Disposes transaction and connection without returning an unowned live link.</summary>
    public void Dispose()
    {
        if (_ownsConnection)
        {
            _transaction?.Dispose();
            _connection.Dispose();
        }
    }
}
