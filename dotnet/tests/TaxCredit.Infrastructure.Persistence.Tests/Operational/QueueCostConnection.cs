using System.Data;
using System.Data.Common;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Data.Sqlite;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

internal sealed class QueueCost
{
    internal long Statements { get; set; }
    internal long Transactions { get; set; }
}

internal sealed class QueueCostConnection(string path, QueueCost cost) : DbConnection
{
    private readonly SqliteConnection _inner = new(new SqliteConnectionStringBuilder { DataSource = path, Pooling = false }.ConnectionString);
    [AllowNull] public override string ConnectionString { get => _inner.ConnectionString; set => _inner.ConnectionString = value; }
    public override string Database => _inner.Database;
    public override string DataSource => _inner.DataSource;
    public override string ServerVersion => _inner.ServerVersion;
    public override ConnectionState State => _inner.State;
    public override void ChangeDatabase(string databaseName) => _inner.ChangeDatabase(databaseName);
    public override void Open() => _inner.Open();
    public override void Close() => _inner.Close();

    protected override DbTransaction BeginDbTransaction(IsolationLevel isolationLevel)
    {
        cost.Transactions++;
        return new Transaction(this, _inner.BeginTransaction(isolationLevel));
    }

    protected override DbCommand CreateDbCommand() => new Command(this, _inner.CreateCommand(), cost);

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _inner.Dispose();
        }

        base.Dispose(disposing);
    }

    private sealed class Transaction(QueueCostConnection connection, DbTransaction inner) : DbTransaction
    {
        internal DbTransaction Inner { get; } = inner;
        public override IsolationLevel IsolationLevel => Inner.IsolationLevel;
        protected override DbConnection DbConnection => connection;
        public override void Commit() => Inner.Commit();
        public override void Rollback() => Inner.Rollback();
        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                Inner.Dispose();
            }

            base.Dispose(disposing);
        }
    }

    private sealed class Command(QueueCostConnection connection, DbCommand inner, QueueCost cost) : DbCommand
    {
        private DbTransaction? _transaction;
        [AllowNull] public override string CommandText { get => inner.CommandText; set => inner.CommandText = value; }
        public override int CommandTimeout { get => inner.CommandTimeout; set => inner.CommandTimeout = value; }
        public override CommandType CommandType { get => inner.CommandType; set => inner.CommandType = value; }
        public override bool DesignTimeVisible { get => inner.DesignTimeVisible; set => inner.DesignTimeVisible = value; }
        public override UpdateRowSource UpdatedRowSource { get => inner.UpdatedRowSource; set => inner.UpdatedRowSource = value; }
        protected override DbConnection? DbConnection { get => connection; set => inner.Connection = value is QueueCostConnection wrapper ? wrapper._inner : value; }
        protected override DbTransaction? DbTransaction
        {
            get => _transaction;
            set
            {
                _transaction = value;
                inner.Transaction = value is Transaction wrapper ? wrapper.Inner : value;
            }
        }

        protected override DbParameterCollection DbParameterCollection => inner.Parameters;
        public override void Cancel() => inner.Cancel();
        public override void Prepare() => inner.Prepare();
        protected override DbParameter CreateDbParameter() => inner.CreateParameter();
        public override int ExecuteNonQuery()
        {
            cost.Statements++;
            return inner.ExecuteNonQuery();
        }

        public override object? ExecuteScalar()
        {
            cost.Statements++;
            return inner.ExecuteScalar();
        }

        protected override DbDataReader ExecuteDbDataReader(CommandBehavior behavior)
        {
            cost.Statements++;
            return inner.ExecuteReader(behavior);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                inner.Dispose();
            }

            base.Dispose(disposing);
        }
    }
}
