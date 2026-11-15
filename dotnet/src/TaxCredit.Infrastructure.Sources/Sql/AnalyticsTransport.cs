using System.Data;
using System.Data.Common;
using Microsoft.Data.SqlClient;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>A planned read contains explicit SQL plus its logical projection for hermetic fixture execution.</summary>
public sealed record AnalyticsQuery(string Sql, IReadOnlyList<object?> Parameters, string Table,
    IReadOnlyDictionary<string, string> Columns, string? FilterField = null,
    IReadOnlyList<object?>? FilterValues = null, string Kind = "scan")
{
    /// <summary>Never print bound values, SQL, or physical names in diagnostics.</summary>
    public override string ToString() => "AnalyticsQuery(" + Kind + ")";
}

/// <summary>Source-only transport; never bound to the operational Warehouse pool.</summary>
public interface IAnalyticsTransport
{
    /// <summary>Provider evidence only; an unknown implementation must not claim live SQL provenance.</summary>
    string SourceProvenance => "unverified-analytics-transport";
    /// <summary>Whether source connection configuration is complete.</summary>
    bool IsConfigured { get; }
    /// <summary>Names in ordinal order; empty is a missing table, exceptions are outages.</summary>
    IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default);
    /// <summary>Streams logical rows; disposal must cancel/close the underlying reader on early exit.</summary>
    IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default);
    /// <summary>One connection for this synchronous execution flow, disposed at the outermost scope.</summary>
    IDisposable SharedScope();
}

/// <summary>Injected acquisition makes credential selection a composition-root decision, not an adapter side effect.</summary>
public interface IAnalyticsTokenProvider
{
    /// <summary>Acquire/refresh the requested database audience, respecting cancellation.</summary>
    Task<AnalyticsAccessToken> AcquireAsync(string scope, CancellationToken cancellationToken);
}

/// <summary>Short-lived credentials; textual rendering is always redacted.</summary>
public sealed class AnalyticsAccessToken(string token, DateTimeOffset expiresOn)
{
    /// <summary>The token, only for the driver.</summary>
    public string Token { get; } = token;
    /// <summary>Expiry used by SqlClient's callback refresh.</summary>
    public DateTimeOffset ExpiresOn { get; } = expiresOn;
    /// <inheritdoc />
    public override string ToString() => "AnalyticsAccessToken(redacted)";
}

/// <summary>Analytics-only configuration; no connection string or secret is accepted.</summary>
public sealed record AnalyticsConnectionOptions(string Server, string Database, int ConnectTimeoutSeconds = 90,
    int CommandTimeoutSeconds = 120, int MaximumPoolSize = 4)
{
    /// <inheritdoc />
    public override string ToString() => "AnalyticsConnectionOptions(redacted)";
}

/// <summary>Encrypted token-authenticated connections with a stable callback identity for a source-only pool.</summary>
public sealed class AnalyticsConnectionFactory
{
    /// <summary>The sole accepted token scope.</summary>
    public const string DatabaseScope = "https://database.windows.net/.default";
    private readonly AnalyticsConnectionOptions _options;
    private readonly Func<SqlAuthenticationParameters, CancellationToken, Task<SqlAuthenticationToken>> _callback;

    /// <summary>No credentials are acquired during construction or connection creation.</summary>
    public AnalyticsConnectionFactory(AnalyticsConnectionOptions options, IAnalyticsTokenProvider tokens, TimeProvider? clock = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(tokens);
        if (options.ConnectTimeoutSeconds < 1 || options.CommandTimeoutSeconds < 1 || options.MaximumPoolSize is < 1 or > 100)
        {
            throw new ArgumentOutOfRangeException(nameof(options));
        }
        _options = options;
        var time = clock ?? TimeProvider.System;
        _callback = async (_, cancellation) =>
        {
            var token = await tokens.AcquireAsync(DatabaseScope, cancellation).ConfigureAwait(false);
            cancellation.ThrowIfCancellationRequested();
            if (string.IsNullOrEmpty(token.Token) || token.ExpiresOn <= time.GetUtcNow())
            {
                throw new SourceUnavailable("source_token");
            }
            return new SqlAuthenticationToken(token.Token, token.ExpiresOn);
        };
    }

    /// <summary>Incomplete configuration is observable without attempting a login.</summary>
    public bool IsConfigured => !string.IsNullOrWhiteSpace(_options.Server) && !string.IsNullOrWhiteSpace(_options.Database);
    /// <summary>Statement timeout, distinct from connection timeout.</summary>
    public int CommandTimeoutSeconds => _options.CommandTimeoutSeconds;

    /// <summary>Creates a closed connection; the callback acquires tokens only when the driver needs them.</summary>
    public SqlConnection Create()
    {
        if (!IsConfigured) { throw new SourceNotConfigured(); }
        var builder = new SqlConnectionStringBuilder
        {
            DataSource = _options.Server,
            InitialCatalog = _options.Database,
            Encrypt = SqlConnectionEncryptOption.Mandatory,
            TrustServerCertificate = false,
            ConnectTimeout = _options.ConnectTimeoutSeconds,
            Pooling = true,
            MaxPoolSize = _options.MaximumPoolSize,
            ApplicationName = "TaxCredit.SourceAnalytics",
            PersistSecurityInfo = false,
        };
        return new SqlConnection(builder.ConnectionString) { AccessTokenCallback = _callback };
    }
}

/// <summary>Sequential-access SQL transport. No raw SQL errors/connection strings escape this boundary.</summary>
public sealed class SqlAnalyticsTransport(AnalyticsConnectionFactory factory) : IAnalyticsTransport, IDisposable
{
    private readonly ThreadLocal<ScopeState?> _scope = new();

    /// <inheritdoc />
    public string SourceProvenance => "sql-analytics";
    /// <inheritdoc />
    public bool IsConfigured => factory.IsConfigured;

    /// <inheritdoc />
    public IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default)
    {
        var query = new AnalyticsQuery(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = @p0 AND TABLE_NAME = @p1 ORDER BY ORDINAL_POSITION",
            [string.IsNullOrWhiteSpace(schema) ? "dbo" : schema, physicalTable], "metadata",
            new Dictionary<string, string> { ["column"] = "COLUMN_NAME" }, Kind: "metadata");
        return Read(query, cancellationToken).Select(r => (string)r["column"]!).ToArray();
    }

    /// <inheritdoc />
    public IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(query);
        using var lease = Acquire(cancellationToken);
        using var command = lease.Connection.CreateCommand();
        command.CommandText = query.Sql;
        command.CommandTimeout = factory.CommandTimeoutSeconds;
        for (var i = 0; i < query.Parameters.Count; i++)
        {
            var value = query.Parameters[i];
            var parameter = command.Parameters.Add("@p" + i, value is string ? SqlDbType.NVarChar : SqlDbType.BigInt);
            parameter.Value = value ?? DBNull.Value;
        }
        using var registration = cancellationToken.Register(command.Cancel);
        using var reader = Execute(command, cancellationToken);
        var names = query.Columns.Keys.ToArray();
        while (Next(reader, cancellationToken))
        {
            yield return Materialize(reader, names, cancellationToken);
        }
    }

    /// <inheritdoc />
    public IDisposable SharedScope()
    {
        if (!IsConfigured) { throw new SourceNotConfigured(); }
        if (_scope.Value is { } state) { state.Depth++; }
        else { _scope.Value = new ScopeState(Open(default)); }
        return new ScopeLease(this);
    }

    /// <summary>Disposes this transport after request scopes have completed.</summary>
    public void Dispose()
    {
        _scope.Value?.Connection.Dispose();
        _scope.Dispose();
    }

    private ConnectionLease Acquire(CancellationToken cancellationToken) =>
        _scope.Value is { } scope ? new ConnectionLease(scope.Connection, false) : new ConnectionLease(Open(cancellationToken), true);

    private SqlConnection Open(CancellationToken cancellationToken)
    {
        var connection = factory.Create();
        try
        {
            connection.OpenAsync(cancellationToken).ConfigureAwait(false).GetAwaiter().GetResult();
            return connection;
        }
        catch (Exception e) when (e is SqlException or TimeoutException)
        {
            connection.Dispose();
            cancellationToken.ThrowIfCancellationRequested();
            throw e is SqlException sql ? SqlFailure(sql.Number) : new SourceUnavailable();
        }
        catch { connection.Dispose(); throw; }
    }

    private static SqlDataReader Execute(SqlCommand command, CancellationToken cancellationToken)
    {
        try { return command.ExecuteReader(CommandBehavior.SequentialAccess); }
        catch (SqlException error) { cancellationToken.ThrowIfCancellationRequested(); throw SqlFailure(error.Number); }
    }

    private static bool Next(DbDataReader reader, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        try { return reader.Read(); }
        catch (SqlException error) { cancellationToken.ThrowIfCancellationRequested(); throw SqlFailure(error.Number); }
    }

    private static Dictionary<string, object?> Materialize(DbDataReader reader, string[] names, CancellationToken cancellationToken)
    {
        try
        {
            var row = new Dictionary<string, object?>(StringComparer.Ordinal);
            for (var i = 0; i < names.Length; i++) { row.Add(names[i], reader.IsDBNull(i) ? null : reader.GetValue(i)); }
            return row;
        }
        catch (SqlException error) { cancellationToken.ThrowIfCancellationRequested(); throw SqlFailure(error.Number); }
    }

    internal static SourceFailureException SqlFailure(int number) => number switch
    {
        207 or 208 => new SourceSchemaMismatch("source_statement", ["metadata_changed"]),
        245 or 8114 => new SourceSchemaMismatch("source_statement", ["column_type"]),
        102 or 156 or 8120 => new SourceQueryRejected(),
        _ => new SourceUnavailable(),
    };

    private void EndScope()
    {
        var state = _scope.Value ?? throw new InvalidOperationException("Scope was disposed on another thread.");
        if (--state.Depth == 0) { state.Connection.Dispose(); _scope.Value = null; }
    }

    private sealed class ScopeState(SqlConnection connection)
    {
        internal SqlConnection Connection { get; } = connection;
        internal int Depth { get; set; } = 1;
    }
    private sealed class ScopeLease(SqlAnalyticsTransport owner) : IDisposable
    {
        private bool _disposed;
        public void Dispose() { if (!_disposed) { owner.EndScope(); _disposed = true; } }
    }
    private sealed class ConnectionLease(SqlConnection connection, bool owned) : IDisposable
    {
        internal SqlConnection Connection { get; } = connection;
        public void Dispose() { if (owned) { Connection.Dispose(); } }
    }
}
