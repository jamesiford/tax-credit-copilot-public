using System.Data.Common;
using System.Diagnostics;
using Microsoft.Data.SqlClient;
using Microsoft.Data.Sqlite;

namespace TaxCredit.Infrastructure.Persistence.Sql;

internal static class BoundedRead
{
    internal static IReadOnlyList<IReadOnlyDictionary<string, object?>> Read(
        DbConnection connection, DbCommand command, int maximumRows, int seconds, Action<string> log, CancellationToken cancellation)
    {
        using var budget = new ReadBudget(connection, command, seconds, log, cancellation);
        try
        {
            budget.Check();
            using var reader = command.ExecuteReader();
            var rows = new List<IReadOnlyDictionary<string, object?>>();
            while (reader.Read())
            {
                budget.Check();
                if (rows.Count == maximumRows)
                {
                    throw new InvalidOperationException("Read exceeded its maximum row count.");
                }

                var row = new Dictionary<string, object?>(StringComparer.Ordinal);
                for (var index = 0; index < reader.FieldCount; index++)
                {
                    row.Add(reader.GetName(index), reader.IsDBNull(index) ? null : reader.GetValue(index));
                }

                rows.Add(row);
            }

            budget.Check();
            return rows;
        }
        catch (DbException error) when (budget.Expired || error is SqlException { Number: -2 })
        {
            cancellation.ThrowIfCancellationRequested();
            throw new TimeoutException("Read exceeded its execution timeout.", error);
        }
    }

    private sealed class ReadBudget : IDisposable
    {
        private readonly CancellationToken _cancellation;
        private readonly CancellationTokenSource _deadline;
        private readonly CancellationTokenRegistration _registration;
        private readonly SqliteConnection? _sqlite;
        private readonly Stopwatch _clock = Stopwatch.StartNew();
        private readonly int _seconds;

        internal ReadBudget(DbConnection connection, DbCommand command, int seconds, Action<string> log, CancellationToken cancellation)
        {
            _seconds = seconds;
            _cancellation = cancellation;
            _deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
            _sqlite = connection as SqliteConnection;
            if (_sqlite is not null)
            {
                SQLitePCL.raw.sqlite3_progress_handler(_sqlite.Handle, 1000,
                    static state => ((ReadBudget)state!).Expired ? 1 : 0, this);
            }

            _registration = _deadline.Token.Register(() => Cancel(command, log));
            _deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        }

        internal bool Expired => _deadline.IsCancellationRequested || _clock.Elapsed.TotalSeconds >= _seconds;

        internal void Check()
        {
            _cancellation.ThrowIfCancellationRequested();
            if (Expired)
            {
                throw new TimeoutException("Read exceeded its execution timeout.");
            }
        }

        private void Cancel(DbCommand command, Action<string> log)
        {
            try
            {
                if (_sqlite is not null)
                {
                    SQLitePCL.raw.sqlite3_interrupt(_sqlite.Handle);
                }
                else
                {
                    command.Cancel();
                }
            }
            catch (DbException error)
            {
                log("read cancellation failed: " + error.GetType().Name);
            }
        }

        public void Dispose()
        {
            _registration.Dispose();
            _deadline.Dispose();
            if (_sqlite is not null)
            {
                SQLitePCL.raw.sqlite3_progress_handler(_sqlite.Handle, 0, null, null);
            }
        }
    }
}
