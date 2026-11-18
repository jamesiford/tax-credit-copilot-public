using System.Data;
using System.Data.Common;
using Microsoft.Data.SqlClient;
using Microsoft.Data.Sqlite;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>One connection per unit of work; no process mutex substitutes for database isolation.</summary>
public sealed class PersistenceDatabase
{
    private readonly Func<DbConnection> _factory;
    private readonly Action<string> _log;
    private readonly Action<TimeSpan> _delay;
    private readonly IReadOnlyList<string> _sourceColumns;
    private readonly AsyncLocal<SqlSession?> _ambient = new();
    private readonly AsyncLocal<List<Action>?> _afterCommit = new();

    /// <summary>Configures a provider and injectable connection/log/retry boundaries.</summary>
    public PersistenceDatabase(Func<DbConnection> factory, ISqlDialect dialect, Action<string>? log = null,
        Action<TimeSpan>? delay = null, IReadOnlyList<string>? sourceColumns = null)
    {
        ArgumentNullException.ThrowIfNull(factory);
        ArgumentNullException.ThrowIfNull(dialect);
        _factory = factory;
        Dialect = dialect;
        _log = log ?? (message => System.Diagnostics.Trace.TraceInformation("{0}", message));
        _delay = delay ?? Thread.Sleep;
        _sourceColumns = sourceColumns ?? ["AccountId"];
    }

    /// <summary>The SQL syntax selected for this destination.</summary>
    public ISqlDialect Dialect { get; }

    /// <summary>Opens an owned connection, closing it even when opening fails.</summary>
    public SqlSession Open()
    {
        if (_ambient.Value is { } existing)
        {
            return existing.Borrow();
        }

        var connection = _factory();
        try
        {
            if (connection.State != ConnectionState.Open)
            {
                connection.Open();
            }

            return new SqlSession(connection, Dialect, _sourceColumns, _log);
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    /// <summary>
    /// Runs <paramref name="work" /> once the outermost transaction has committed, or at once when none is open. It never runs after a rollback or an
    /// ambiguous commit, and a failure in it is logged, never thrown: it is housekeeping that must not change the outcome of what it follows.
    /// </summary>
    public void AfterCommit(Action work)
    {
        ArgumentNullException.ThrowIfNull(work);
        if (_ambient.Value is null)
        {
            Housekeeping(work);
            return;
        }

        (_afterCommit.Value ??= []).Add(work);
    }

    private void Housekeeping(Action work)
    {
        try
        {
            work();
        }
        catch (Exception error)
        {
            _log("Post-commit housekeeping failed and was skipped: " + error.GetType().Name + ": " + error.Message);
        }
    }

    /// <summary>
    /// Retries only a confirmed aborted native-conflict transaction, never an ambiguous commit. <paramref name="deferWriteLock" /> lets SQLite take its
    /// single write lock at the first write instead of at BEGIN, so a long transaction that is still computing does not block other connections (lease renewal).
    /// </summary>
    public T Transact<T>(Func<SqlSession, T> work, int attempts = 5, bool deferWriteLock = false)
    {
        ArgumentNullException.ThrowIfNull(work);
        ArgumentOutOfRangeException.ThrowIfLessThan(attempts, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(attempts, 10);
        if (_ambient.Value is { } current)
        {
            return work(current);
        }

        for (var attempt = 1; ; attempt++)
        {
            using var session = Open();
            T result;
            _afterCommit.Value = null;
            try
            {
                session.Begin(deferWriteLock);
                _ambient.Value = session;
                result = work(session);
            }
            catch (Exception error)
            {
                _afterCommit.Value = null;
                session.Rollback();
                if (!SqlConflicts.IsAbortedConflict(error) || attempt == attempts)
                {
                    throw;
                }

                _log("Rolled back write conflict; retrying transaction.");
                _delay(TimeSpan.FromMilliseconds(Math.Min(3200, 200 * Math.Pow(2, attempt - 1))));
                continue;
            }
            finally
            {
                _ambient.Value = null;
            }

            try
            {
                session.Commit();
            }
            catch (Exception error) when (!SqlConflicts.IsAbortedConflict(error))
            {
                _afterCommit.Value = null;
                throw new AmbiguousCommitException("Commit outcome is unknown; reconcile the operation identity before retry.", error);
            }
            catch
            {
                _afterCommit.Value = null;
                session.Rollback();
                if (attempt == attempts)
                {
                    throw;
                }

                _delay(TimeSpan.FromMilliseconds(Math.Min(3200, 200 * Math.Pow(2, attempt - 1))));
                continue;
            }

            var pending = _afterCommit.Value;
            _afterCommit.Value = null;
            foreach (var queued in pending ?? [])
            {
                Housekeeping(queued);
            }

            return result;
        }
    }

    /// <summary>Creates a file-backed hermetic destination with exact-decimal SQL functions.</summary>
    public static PersistenceDatabase Sqlite(string path, Action<string>? log = null, Domain.DataMap.PhysicalNames? names = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        var settings = new SqliteConnectionStringBuilder { DataSource = path, Pooling = false, DefaultTimeout = 30 };
        return new PersistenceDatabase(() =>
        {
            var connection = new SqliteConnection(settings.ConnectionString);
            // Write-ahead logging lets a lease renewal (its own connection) commit while a long transaction has only read, instead of waiting for it.
            connection.Open();
            using (var pragma = connection.CreateCommand())
            {
                pragma.CommandText = "PRAGMA journal_mode=WAL";
                pragma.ExecuteNonQuery();
            }

            connection.CreateCollation("TCC_DECIMAL", (a, b) => PyDecimalOps.Compare(PyDecimal.Parse(a), PyDecimal.Parse(b)));
            connection.CreateAggregate<string?, PyDecimal, string>("tcc_decimal_sum", PyDecimal.Parse("0"),
                (sum, value) => value is null ? sum : PyDecimalOps.Add(sum, PyDecimal.Parse(value)), sum => sum.ToString());
            connection.CreateFunction<string?, int, int, bool>("tcc_decimal_valid", (value, precision, scale) =>
            {
                if (value is null)
                {
                    return true;
                }

                var number = PyDecimal.Parse(value);
                var fixedValue = number.Quantize(scale, PyRoundingMode.HalfEven);
                return PyDecimalOps.Compare(number, fixedValue) == 0
                    && fixedValue.Coefficient.ToString(System.Globalization.CultureInfo.InvariantCulture).Length <= precision;
            });
            return connection;
        }, names is null ? new SqliteDialect() : new SqliteDialect(names), log);
    }
}

/// <summary>An unknown commit result requires identity reconciliation, not a replayed insert.</summary>
public sealed class AmbiguousCommitException(string message, Exception innerException) : InvalidOperationException(message, innerException);

internal static class SqlConflicts
{
    internal static bool IsAbortedConflict(Exception error) => error switch
    {
        SqlException sql => sql.Errors.Cast<SqlError>().Any(e => e.Number is 24556 or 3960 or 1205),
        SqliteException sqlite => sqlite.SqliteErrorCode is 5 or 6,
        NativeSqlException native => native.Number is 24556 or 3960 or 1205,
        _ => false,
    };
}

internal sealed class NativeSqlException(int number) : DbException("Injected native SQL failure.")
{
    internal int Number { get; } = number;
}
