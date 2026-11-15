using System.Text.Json;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class AggregateSqlBoundaryTests
{
    [Theory]
    [InlineData("period_end", "worksite_then_location")]
    [InlineData("exclude", "worksite_then_location")]
    [InlineData("period_end", "worksite_only")]
    [InlineData("period_end", "location_only")]
    public void ActualAggregateSqlRunsOfflineWithEveryNamedTransform(string dateMode, string siteMode)
    {
        var mapping = SourceMapping.Load("{\"transforms\":{\"null_pay_date\":\"" + dateMode
            + "\",\"worksite_location\":\"" + siteMode + "\"}}");
        var tables = SourceTestData.MiniTables(mapping);
        if (siteMode != "worksite_then_location") { ((Dictionary<string, object?>)tables["Payroll"][0])["WorksiteLocationId"] = 0L; }
        var (source, scanner, _) = SourceTestData.Source(tables, mapping);
        var rows = source.LoadPayPeriods(7);
        using var result = ExecuteSql(tables, scanner);
        var observations = result.RootElement.EnumerateArray().ToArray();
        Assert.Equal(rows.Count, observations.Sum(r => r[3].GetInt32()));
        Assert.Equal(rows.Select(r => (string)r.Get("Work_State")!).Distinct().Order(StringComparer.Ordinal),
            observations.Select(r => r[1].GetString()!).Distinct().Order(StringComparer.Ordinal));
        Assert.Equal(rows.Select(r => (string)r.Get("Pay_Date")!).Distinct().Order(StringComparer.Ordinal),
            observations.Select(r => r[2].GetString()!).Distinct().Order(StringComparer.Ordinal));
    }

    [Fact]
    public void NeedsHumanPythonProjectionAndSqlDisagreeForZeroWorksiteWithoutRepricingEither()
    {
        var tables = SourceTestData.MiniTables();
        var payroll = (Dictionary<string, object?>)tables["Payroll"][0];
        payroll["WorksiteLocationId"] = 0L;
        tables["Payroll"] = [payroll];
        var (source, scanner, _) = SourceTestData.Source(tables);
        var projected = Assert.Single(source.LoadPayPeriods(7));
        Assert.Equal("SC", projected.Get("Work_State"));
        Assert.Equal("SC_site", projected.Get("Worksite_ID"));
        using var python = SourceTestData.Oracle("projection", new { tables, accounts = new[] { 7L } });
        Assert.Equal("SC", python.RootElement[0].GetProperty("projected")[0].GetProperty("Work_State").GetString());
        using var sql = ExecuteSql(tables, scanner);
        var observation = Assert.Single(sql.RootElement.EnumerateArray());
        Assert.Equal("", observation[1].GetString());
        Assert.Equal(1, observation[3].GetInt32());
        Assert.Empty(source.PayrollScope(7).States);
        Assert.Empty(source.Footprint()[7]);
        Assert.Contains("COALESCE(p.[WorksiteLocationId], p.[LocationId])", new SourceQueries(scanner).Scope(7).Sql, StringComparison.Ordinal);
    }

    private static JsonDocument ExecuteSql(
        Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> tables, SourceScanner scanner)
    {
        var query = new SourceQueries(scanner).Scope(7);
        return SourceTestData.Oracle("sql", new
        {
            tables,
            schema = scanner.Schema,
            sql = query.Sql,
            parameters = query.Parameters,
            columns = scanner.Mapping.Tables.ToDictionary(t => t.Value.Physical, t => t.Value.Fields.Values.Select(f => f.Column).ToArray()),
        });
    }
}
