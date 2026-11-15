using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

/// <summary>Tenant-bound read models over the seven Gold tables; no payroll reader or engine is invoked.</summary>
public sealed partial class GoldReader : IGoldReadPort
{
    private readonly PersistenceDatabase _database;
    private readonly AsyncLocal<SqlSession?> _scope = new();
    private readonly TimeProvider _clock;
    private readonly TimeSpan _strandedAfter;

    /// <summary>Uses an injectable clock to keep stranded manifests from claiming to be running forever.</summary>
    public GoldReader(PersistenceDatabase database, TimeProvider? clock = null, TimeSpan? strandedAfter = null)
    {
        ArgumentNullException.ThrowIfNull(database);
        _database = database;
        _clock = clock ?? TimeProvider.System;
        _strandedAfter = (strandedAfter ?? TimeSpan.FromMinutes(60)).Duration();
        Connection = new GoldConnection(database);
    }

    /// <inheritdoc />
    public IGoldConnection Connection { get; }
    /// <inheritdoc />
    public IDisposable Scope()
    {
        var previous = _scope.Value;
        var opened = _database.Open();
        _scope.Value = opened;
        return new ReadScope(() => { _scope.Value = previous; opened.Dispose(); });
    }

    private List<IReadOnlyDictionary<string, object?>> Many(long clientId, string sql, params object?[] values)
    {
        if (_scope.Value is { } held)
        {
            return held.Query(clientId, sql, values).Select(GoldValues.Shape).Cast<IReadOnlyDictionary<string, object?>>().ToList();
        }
        using var session = _database.Open();
        return session.Query(clientId, sql, values).Select(GoldValues.Shape).Cast<IReadOnlyDictionary<string, object?>>().ToList();
    }

    private IReadOnlyDictionary<string, object?>? One(long clientId, string sql, params object?[] values) =>
        Many(clientId, sql, values).FirstOrDefault();
    private string Page(string sql, int limit, int offset = 0) => _database.Dialect.Page(sql, limit, offset);
    private string Sum(string column) => _database.Dialect is SqliteDialect ?
        $"CASE WHEN COUNT({column}) = 0 THEN NULL ELSE tcc_decimal_sum({column}) END" : $"SUM({column})";
    private static string Program(string? code, List<object?> values)
    {
        if (string.IsNullOrEmpty(code))
        {
            return "";
        }
        values.Add(code);
        return " AND program_code = ?";
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?>? LatestRun(long clientId, string? programCode = null)
    {
        var values = new List<object?>();
        var narrow = Program(programCode, values);
        return One(clientId, Page("SELECT run_id, client_id, program_code, tax_year, fiscal_year_begin, fiscal_year_end, " +
            "step1_assumption_set_id, onezero_assumption_set_id, rule_pack_version, code_commit, calculation_id, " +
            "run_started_at, run_completed_at, run_status, superseded_by_run_id, triggered_by " +
            "FROM tcc_ops.run_manifest WHERE {tenant} AND run_status = 'success'" + narrow +
            " AND superseded_by_run_id IS NULL AND run_completed_at IS NOT NULL ORDER BY run_started_at DESC", 1), values.ToArray());
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, object?>? RunInFlight(long clientId) =>
        One(clientId, Page("SELECT run_id, run_started_at, triggered_by, tax_year FROM tcc_ops.run_manifest " +
            "WHERE {tenant} AND run_completed_at IS NULL AND run_status = 'running' " +
            "AND run_started_at >= ? ORDER BY run_started_at DESC", 1),
            (_clock.GetUtcNow() - _strandedAfter).UtcDateTime);

    private sealed class ReadScope(Action close) : IDisposable
    {
        private Action? _close = close;
        public void Dispose() => Interlocked.Exchange(ref _close, null)?.Invoke();
    }

    private sealed class GoldConnection(PersistenceDatabase database) : IGoldConnection
    {
        public int Keepalive()
        {
            using var session = database.Open();
            session.Query(0, "SELECT COUNT(*) AS total FROM tcc_ops.run_manifest WHERE {tenant} AND 1 = 0");
            return 1;
        }
        public int Prewarm(int count = 1)
        {
            ArgumentOutOfRangeException.ThrowIfNegative(count);
            var sessions = new List<SqlSession>();
            try
            {
                for (var i = 0; i < count; i++)
                {
                    var session = database.Open();
                    sessions.Add(session);
                    session.Query(0, "SELECT COUNT(*) AS total FROM tcc_ops.run_manifest WHERE {tenant} AND 1 = 0");
                }
                return sessions.Count;
            }
            finally
            {
                foreach (var session in sessions)
                {
                    session.Dispose();
                }
            }
        }
    }
}
