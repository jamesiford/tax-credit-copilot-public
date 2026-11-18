using System.Data.Common;
using System.Numerics;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

public sealed class BulkLoadTests
{
    private sealed class RecordingWriter(bool canWrite = true) : IBulkWriter
    {
        internal List<(string Table, IReadOnlyList<string> Columns, IReadOnlyList<IReadOnlyList<object?>> Rows)> Loads { get; } = [];
        public bool CanWrite(DbConnection connection, IReadOnlyList<IReadOnlyList<object?>> rows) => canWrite;

        public int Write(DbConnection connection, DbTransaction? transaction, string table, IReadOnlyList<string> columns,
            IReadOnlyList<IReadOnlyList<object?>> rows, BulkLoadPolicy policy)
        {
            Loads.Add((table, columns, rows));
            return rows.Count;
        }
    }

    private static IReadOnlyList<object?>[] Rows(int count) =>
        Enumerable.Range(0, count).Select(i => (IReadOnlyList<object?>)new object?[] { 7L, "e" + i }).ToArray();

    private static (RecordingConnection Connection, RecordingWriter Writer, SqlSession Session) Open(BulkLoadPolicy policy, bool canWrite = true)
    {
        var connection = new RecordingConnection();
        var writer = new RecordingWriter(canWrite);
        var session = new PersistenceDatabase(() => connection, new SqlServerDialect(policy, writer)).Open();
        return (connection, writer, session);
    }

    [Fact]
    public void A_large_insert_is_one_bulk_load_in_row_order_and_sends_no_statements()
    {
        var (connection, writer, session) = Open(new BulkLoadPolicy(true, 10, 60));
        using (session)
        {
            Assert.Equal(5000, session.Insert(7, "tcc_gold.employee_period_fact", ["client_id", "employee_id"], Rows(5000)));
        }

        var load = Assert.Single(writer.Loads);
        Assert.Equal("[tcc_gold].[employee_period_fact]", load.Table);
        Assert.Equal(Enumerable.Range(0, 5000).Select(i => "e" + i), load.Rows.Select(r => (string)r[1]!));
        Assert.Empty(connection.Commands);
    }

    [Theory]
    [InlineData(true, 10, 9, true)]
    [InlineData(false, 10, 5000, true)]
    [InlineData(true, 10, 5000, false)]
    public void Statements_remain_the_path_for_small_inserts_a_disabled_policy_or_an_unsupported_connection(bool enabled, int minimum, int rows, bool canWrite)
    {
        var (connection, writer, session) = Open(new BulkLoadPolicy(enabled, minimum, 60), canWrite);
        using (session)
        {
            session.Insert(7, "tcc_gold.employee_period_fact", ["client_id", "employee_id"], Rows(rows));
        }

        Assert.Empty(writer.Loads);
        Assert.Equal((rows + 499) / 500, connection.Commands.Count);
    }

    [Fact]
    public void Every_row_is_tenant_checked_before_any_bulk_byte_is_sent()
    {
        var (connection, writer, session) = Open(new BulkLoadPolicy(true, 10, 60));
        var rows = Rows(100).Append(new object?[] { 8L, "foreign" }).ToArray();
        using (session)
        {
            Assert.Throws<TenantScopeViolation>(() => session.Insert(7, "tcc_gold.employee_period_fact", ["client_id", "employee_id"], rows));
        }

        Assert.Empty(writer.Loads);
        Assert.Empty(connection.Commands);
    }

    [Fact]
    public void The_policy_reads_its_settings_and_refuses_nonsense()
    {
        Assert.Equal(BulkLoadPolicy.Default, BulkLoadPolicy.FromSettings(_ => null));
        var off = BulkLoadPolicy.FromSettings(key => key == "TCC_BULK_LOAD" ? "off" : null);
        Assert.False(off.Enabled);
        var tuned = BulkLoadPolicy.FromSettings(key => key switch { "TCC_BULK_LOAD_MIN_ROWS" => "250", "TCC_BULK_TIMEOUT_SECONDS" => "90", _ => null });
        Assert.Equal(new BulkLoadPolicy(true, 250, 90), tuned);
        Assert.Throws<InvalidOperationException>(() => BulkLoadPolicy.FromSettings(key => key == "TCC_BULK_LOAD" ? "maybe" : null));
        Assert.Throws<InvalidOperationException>(() => BulkLoadPolicy.FromSettings(key => key == "TCC_BULK_TIMEOUT_SECONDS" ? "0" : null));
        Assert.False(new SqliteDialect().Bulk.Enabled);
    }

    [Fact]
    public void Bulk_cells_convert_the_way_statement_parameters_do()
    {
        Assert.Equal(DBNull.Value, BulkRows.Convert(null));
        Assert.Equal(42L, BulkRows.Convert(new BigInteger(42)));
        Assert.Equal(new DateTime(2026, 7, 4), BulkRows.Convert(new DateOnly(2026, 7, 4)));
        var money = Assert.IsType<decimal>(BulkRows.Convert(PyDecimal.Parse("-1234.50")));
        Assert.Equal("-1234.50", money.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var whole = Assert.IsType<decimal>(BulkRows.Convert(PyDecimal.Parse("1E+2")));
        Assert.Equal(100m, whole);
        Assert.Equal("text", BulkRows.Convert("text"));
        Assert.False(BulkRows.Representable(PyDecimal.Parse("1." + new string('0', 30))));
        Assert.False(BulkRows.Representable(PyDecimal.Parse(new string('9', 30))));
        Assert.True(BulkRows.Representable(PyDecimal.Parse("79228162514264337593543950335")));
    }

    [Fact]
    public void Gold_on_a_sql_server_family_target_is_identical_through_statements_and_bulk()
    {
        using var target = SqlServerTarget.TryCreate();
        if (target is null) { return; }
        var payload = SyntheticGold.Payload(2500, "dump-run");
        new GoldWriter(target.Database(BulkLoadPolicy.Off), PersistenceFixture.Root).WriteRun(payload);
        using var bulkTarget = SqlServerTarget.TryCreate()!;
        var bulk = new GoldWriter(bulkTarget.Database(new BulkLoadPolicy(true, 1, 600)), PersistenceFixture.Root);
        bulk.WriteRun(payload);
        Assert.Empty(bulk.Validate());
        Assert.Equal(SqlServerTarget.Dump(target.Database(BulkLoadPolicy.Off), 1001), SqlServerTarget.Dump(bulkTarget.Database(BulkLoadPolicy.Off), 1001));
    }

    [Theory]
    [InlineData("prior-current-retired")]
    [InlineData("employee_period_fact")]
    [InlineData("unit_credit_installment")]
    public void A_failed_bulk_publish_leaves_no_rows_and_no_current_flip(string checkpoint)
    {
        using var target = SqlServerTarget.TryCreate();
        if (target is null) { return; }
        var database = target.Database(new BulkLoadPolicy(true, 1, 600));
        var first = SyntheticGold.Payload(2500, "first-run");
        new GoldWriter(database, PersistenceFixture.Root).WriteRun(first);
        var replacement = SyntheticGold.Payload(2500, "failed-replacement");
        var writer = new GoldWriter(database, PersistenceFixture.Root, stage =>
        {
            if (stage == checkpoint)
            {
                throw new IOException("Injected publication failure.");
            }
        });
        Assert.Throws<IOException>(() => writer.WriteRun(replacement));
        using var read = database.Open();
        Assert.Empty(read.Query(1001, "SELECT run_id FROM tcc_gold.employee_period_fact WHERE {tenant} AND run_id=?", replacement.RunId));
        Assert.NotEmpty(read.Query(1001, "SELECT run_id FROM tcc_gold.unit_year_master WHERE {tenant} AND is_current=1 AND run_id=?", first.RunId));
        Assert.Equal("failed", Assert.Single(read.Query(1001, "SELECT run_status FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", replacement.RunId))["run_status"]);
        Assert.Equal("success", Assert.Single(read.Query(1001, "SELECT run_status FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", first.RunId))["run_status"]);
        Assert.Equal(2500, read.Query(1001, "SELECT run_id FROM tcc_gold.employee_period_fact WHERE {tenant} AND run_id=?", first.RunId).Count);
    }
}
