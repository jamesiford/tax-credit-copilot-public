using System.Collections;
using System.Data;
using System.Data.Common;
using System.Diagnostics.CodeAnalysis;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

internal sealed class RecordingConnection : DbConnection
{
    private ConnectionState _state;
    internal List<(string Sql, object?[] Values)> Commands { get; } = [];
    internal int Commits { get; private set; }
    internal int Rollbacks { get; private set; }
    internal bool WasDisposed { get; private set; }
    internal Exception? OpenError { get; set; }
    internal Exception? CommitError { get; set; }
    internal Exception? ExecuteError { get; set; }
    [AllowNull] public override string ConnectionString { get; set; } = string.Empty;
    public override string Database => "synthetic";
    public override string DataSource => "fake";
    public override string ServerVersion => "1";
    public override ConnectionState State => _state;
    public override void ChangeDatabase(string databaseName) => throw new NotSupportedException();
    public override void Close() => _state = ConnectionState.Closed;
    public override void Open()
    {
        if (OpenError is { } error)
        {
            throw error;
        }

        _state = ConnectionState.Open;
    }

    protected override DbTransaction BeginDbTransaction(IsolationLevel isolationLevel) => new Transaction(this, isolationLevel);
    protected override DbCommand CreateDbCommand() => new Command(this);
    protected override void Dispose(bool disposing)
    {
        WasDisposed = true;
        base.Dispose(disposing);
    }

    private sealed class Transaction(RecordingConnection connection, IsolationLevel isolation) : DbTransaction
    {
        public override IsolationLevel IsolationLevel => isolation;
        protected override DbConnection DbConnection => connection;
        public override void Commit()
        {
            connection.Commits++;
            if (connection.CommitError is { } error)
            {
                throw error;
            }
        }

        public override void Rollback() => connection.Rollbacks++;
    }

    private sealed class Command(RecordingConnection connection) : DbCommand
    {
        private readonly Parameters _parameters = new();
        [AllowNull] public override string CommandText { get; set; } = string.Empty;
        public override int CommandTimeout { get; set; }
        public override CommandType CommandType { get; set; }
        public override bool DesignTimeVisible { get; set; }
        public override UpdateRowSource UpdatedRowSource { get; set; }
        protected override DbConnection? DbConnection { get; set; } = connection;
        protected override DbTransaction? DbTransaction { get; set; }
        protected override DbParameterCollection DbParameterCollection => _parameters;
        public override void Cancel() => throw new NotSupportedException();
        public override void Prepare() => throw new NotSupportedException();
        protected override DbParameter CreateDbParameter() => new Parameter();
        public override int ExecuteNonQuery()
        {
            connection.Commands.Add((CommandText, _parameters.Values.Select(p => p.Value).ToArray()));
            if (connection.ExecuteError is { } error)
            {
                throw error;
            }

            return 1;
        }

        public override object? ExecuteScalar() => throw new NotSupportedException();
        protected override DbDataReader ExecuteDbDataReader(CommandBehavior behavior)
        {
            ExecuteNonQuery();
            return new DataTable().CreateDataReader();
        }
    }

    private sealed class Parameter : DbParameter
    {
        public override DbType DbType { get; set; }
        public override ParameterDirection Direction { get; set; } = ParameterDirection.Input;
        public override bool IsNullable { get; set; }
        [AllowNull] public override string ParameterName { get; set; } = string.Empty;
        [AllowNull] public override string SourceColumn { get; set; } = string.Empty;
        public override object? Value { get; set; }
        public override bool SourceColumnNullMapping { get; set; }
        public override int Size { get; set; }
        public override void ResetDbType() => DbType = DbType.Object;
    }

    private sealed class Parameters : DbParameterCollection
    {
        internal List<DbParameter> Values { get; } = [];
        public override int Count => Values.Count;
        public override object SyncRoot => this;
        public override int Add(object value) { Values.Add((DbParameter)value); return Values.Count - 1; }
        public override void AddRange(Array values) { foreach (var value in values) { Add(value!); } }
        public override void Clear() => Values.Clear();
        public override bool Contains(object value) => Values.Contains((DbParameter)value);
        public override bool Contains(string value) => IndexOf(value) >= 0;
        public override void CopyTo(Array array, int index) => ((ICollection)Values).CopyTo(array, index);
        public override IEnumerator GetEnumerator() => Values.GetEnumerator();
        public override int IndexOf(object value) => Values.IndexOf((DbParameter)value);
        public override int IndexOf(string parameterName) => Values.FindIndex(p => p.ParameterName == parameterName);
        public override void Insert(int index, object value) => Values.Insert(index, (DbParameter)value);
        public override void Remove(object value) => Values.Remove((DbParameter)value);
        public override void RemoveAt(int index) => Values.RemoveAt(index);
        public override void RemoveAt(string parameterName) => RemoveAt(IndexOf(parameterName));
        protected override DbParameter GetParameter(int index) => Values[index];
        protected override DbParameter GetParameter(string parameterName) => Values[IndexOf(parameterName)];
        protected override void SetParameter(int index, DbParameter value) => Values[index] = value;
        protected override void SetParameter(string parameterName, DbParameter value) => SetParameter(IndexOf(parameterName), value);
    }
}
