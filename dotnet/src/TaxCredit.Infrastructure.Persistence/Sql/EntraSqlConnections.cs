using Microsoft.Data.SqlClient;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>Token acquisition is injected; the adapter never stores credentials.</summary>
public interface IEntraSqlTokenProvider
{
    /// <summary>Acquires or refreshes an Entra token for the SQL audience.</summary>
    ValueTask<SqlAccessToken> Acquire(string scope, CancellationToken cancellationToken);
}

/// <summary>A transient token and its expiry, retained only by the transport in memory.</summary>
public sealed record SqlAccessToken(string Value, DateTimeOffset ExpiresOn);

/// <summary>SQL Server, Azure SQL and Warehouse share encrypted SqlClient connections.</summary>
public sealed class EntraSqlConnections
{
    private readonly string _connectionString;
    private readonly Func<SqlAuthenticationParameters, CancellationToken, Task<SqlAuthenticationToken>> _callback;

    /// <summary>The only SQL token audience.</summary>
    public const string Scope = "https://database.windows.net/.default";

    /// <summary>Configures a non-secret destination and an injected identity provider.</summary>
    public EntraSqlConnections(string server, string database, IEntraSqlTokenProvider tokens, int maximumPoolSize = 4)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(server);
        ArgumentException.ThrowIfNullOrWhiteSpace(database);
        ArgumentNullException.ThrowIfNull(tokens);
        ArgumentOutOfRangeException.ThrowIfLessThan(maximumPoolSize, 1);
        _connectionString = new SqlConnectionStringBuilder
        {
            DataSource = server,
            InitialCatalog = database,
            Encrypt = SqlConnectionEncryptOption.Mandatory,
            TrustServerCertificate = false,
            ConnectTimeout = 90,
            Pooling = true,
            MaxPoolSize = maximumPoolSize,
            PersistSecurityInfo = false,
        }.ConnectionString;
        _callback = async (_, cancellation) =>
        {
            var token = await tokens.Acquire(Scope, cancellation).ConfigureAwait(false);
            if (string.IsNullOrWhiteSpace(token.Value) || token.ExpiresOn <= DateTimeOffset.UtcNow)
            {
                throw new InvalidOperationException("SQL identity provider returned an unusable token.");
            }

            return new SqlAuthenticationToken(token.Value, token.ExpiresOn);
        };
    }

    /// <summary>Creates an unopened disposable connection; SqlClient invokes the same callback on token refresh.</summary>
    public SqlConnection Create() => new(_connectionString) { AccessTokenCallback = _callback };

    /// <summary>Creates the persistence boundary without exposing a credential-bearing connection string.</summary>
    public PersistenceDatabase Database(Action<string>? log = null) => new(Create, new SqlServerDialect(), log);
}
