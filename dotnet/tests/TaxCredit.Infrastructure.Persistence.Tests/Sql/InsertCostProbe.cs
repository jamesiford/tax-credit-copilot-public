using System.Diagnostics;
using System.Globalization;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;
using Xunit.Abstractions;

namespace TaxCredit.Infrastructure.Persistence.Tests.Sql;

/// <summary>Opt-in (<c>BENCH_RUN=1</c>): where does SQLite spend a Gold insert, in the CHECK functions, the index or the statement itself?</summary>
public sealed class InsertCostProbe(ITestOutputHelper output)
{
    private const int Rows = 20_000;

    [Fact]
    [Trait("Category", "bench")]
    public void Gold_insert_cost_by_constraint()
    {
        if (Environment.GetEnvironmentVariable("BENCH_RUN") != "1") { return; }
        using var fixture = new PersistenceFixture();
        var schema = PersistenceSchema.Read(PersistenceFixture.Root)["tcc_gold.employee_period_fact"];
        var columns = GoldColumns.All["employee_period_fact"];
        var rows = Enumerable.Range(0, Rows).Select(i => (IReadOnlyList<object?>)schema.Select(c => Value(c, i)).ToArray()).ToArray();
        fixture.Database.Transact(s =>
        {
            s.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE probe_plain (" + string.Join(",", schema.Select(c => "\"" + c.Name + "\" " + Type(c))) + ") STRICT");
            s.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE probe_index (" + string.Join(",", schema.Select(c => "\"" + c.Name + "\" " + Type(c))) + ") STRICT");
            s.ExecuteExempt(SqlExemption.Schema, "CREATE INDEX ix_probe ON probe_index (client_id,run_id,tax_year)");
            return 0;
        });
        output.WriteLine(Time(fixture, "real schema (CHECKs + index)", "tcc_gold.employee_period_fact", columns, rows));
        output.WriteLine(Time(fixture, "same columns, no CHECK, no index", "probe_plain", columns, rows));
        output.WriteLine(Time(fixture, "same columns, no CHECK, index", "probe_index", columns, rows));
    }

    private static string Time(PersistenceFixture fixture, string label, string table, IReadOnlyList<string> columns, IReadOnlyList<object?>[] rows)
    {
        var watch = Stopwatch.StartNew();
        fixture.Database.Transact(s => table.StartsWith("probe", StringComparison.Ordinal)
            ? s.InsertExempt(SqlExemption.Schema, table, columns, rows) : s.Insert(1, table, columns, rows));
        return string.Create(CultureInfo.InvariantCulture, $"{label,-36} {watch.Elapsed.TotalMilliseconds,9:F0} ms for {rows.Length:N0} rows");
    }

    private static string Text(string value, int limit) => value.Length <= limit ? value : value[..limit];

    private static string Type(StorageColumn c) => c.SqlType is "BIGINT" or "INT" or "BIT" ? "INTEGER" : "TEXT";

    private static object? Value(StorageColumn c, int i) => c.Name switch
    {
        "client_id" => 1L,
        "tax_year" => 2024L,
        _ => c.SqlType switch
        {
            "BIGINT" or "INT" or "BIT" => 1L,
            "DATE" => "2024-01-0" + (1 + (i % 9)).ToString(CultureInfo.InvariantCulture),
            "DECIMAL" => PyDecimal.Parse("40.00").ToString(),
            _ => Text(c.Name + i.ToString(CultureInfo.InvariantCulture), c.Precision ?? 8),
        },
    };
}
