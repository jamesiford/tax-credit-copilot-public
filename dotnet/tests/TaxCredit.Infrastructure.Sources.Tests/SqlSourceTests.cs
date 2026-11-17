using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class SqlSourceTests
{
    [Fact]
    public void TenantPayrollReadIsOneProjectedFilteredStatementNeverSelectStar()
    {
        var (source, _, transport) = SourceTestData.Source();
        Assert.Equal(2, source.LoadPayPeriods(7).Count);
        var payroll = Assert.Single(transport.Queries, q => q.Table == "Payroll");
        Assert.DoesNotContain("*", payroll.Sql, StringComparison.Ordinal);
        Assert.Contains("WHERE [AccountId] = @p0", payroll.Sql, StringComparison.Ordinal);
        Assert.Equal(7L, Assert.Single(payroll.Parameters));
        Assert.DoesNotContain("7", payroll.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("HourlyRate", payroll.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("ClientEmployeeId", payroll.Sql, StringComparison.Ordinal);
    }

    [Fact]
    public void KeyedDimensionIdsAreSortedBatchedBoundedAndCannotFallBackToWholeTable()
    {
        var (_, scanner, transport) = SourceTestData.Source();
        scanner.Scan("Address", key: "address_id", ids: Enumerable.Range(1, 1999).Select(i => (long)i).Reverse());
        Assert.Equal(3, transport.Queries.Count);
        Assert.All(transport.Queries, q =>
        {
            Assert.InRange(q.Parameters.Count, 1, SourceScanner.IdBatchSize);
            Assert.Contains(" IN (", q.Sql, StringComparison.Ordinal);
        });
        Assert.Equal(1L, transport.Queries[0].Parameters[0]);
        var count = transport.Queries.Count;
        Assert.Empty(scanner.Scan("Address", key: "address_id", ids: []));
        Assert.Equal(count, transport.Queries.Count);
        Assert.Throws<ArgumentException>(() => scanner.Scan("Address", 7));
        Assert.Throws<ArgumentException>(() => scanner.Scan("Payroll"));
        Assert.Throws<ArgumentException>(() => scanner.Scan("Entity"));
    }

    [Fact]
    public void RenamedCasedReservedIdentifiersReachEverySelectAndAggregate()
    {
        var mapping = SourceMapping.Load("""
            {"naming":{"table_prefix":"zz_","table_case":"lower"},"tables":{
            "Payroll":{"table":"PayRoll_Facts","fields":{"account_id":{"column":"Accountid"},"pay_date":{"column":"PaycheckDate"}}},
            "Location":{"fields":{"client_location_id":{"column":"union"}}}}}
            """);
        var (source, _, transport) = SourceTestData.Source(mapping: mapping);
        Assert.Equal(2, source.LoadPayPeriods(7).Count);
        _ = source.PayrollScope(7);
        var payroll = Assert.Single(transport.Queries, q => q.Table == "Payroll" && q.Kind == "scan");
        Assert.Contains("[zz_payroll_facts]", payroll.Sql, StringComparison.Ordinal);
        Assert.Contains("[Accountid]", payroll.Sql, StringComparison.Ordinal);
        Assert.Contains("[PaycheckDate]", payroll.Sql, StringComparison.Ordinal);
        Assert.Contains(transport.Queries, q => q.Sql.Contains("[union]", StringComparison.Ordinal));
        Assert.DoesNotContain(transport.Queries, q => q.Sql.Contains("[PayDate]", StringComparison.Ordinal));
        Assert.Equal("[a]]b]", SourceMapping.Quote("a]b"));
    }

    [Theory]
    [InlineData("{\"tables\":{\"Payroll\":{\"fields\":{\"hours\":{\"column\":\"Hours; DROP TABLE x\"}}}}}")]
    [InlineData("{\"tables\":{\"Payroll\":{\"drop_fields\":[\"account_id\"]}}}")]
    [InlineData("{\"tables\":{\"Payroll\":{\"tenant_field\":null}}}")]
    [InlineData("{\"tables\":{\"Payroll\":{\"fields\":{\"account_id\":{\"required\":false}}}}}")]
    [InlineData("{\"tables\":{\"Payroll\":{\"fields\":{\"unknown\":{\"column\":\"X\"}}}}}")]
    [InlineData("{\"tables\":{\"Payroll\":{\"fields\":{\"hours\":{\"type\":\"varchar\"}}}}}")]
    [InlineData("{\"transforms\":{\"null_pay_date\":\"guess\"}}")]
    public void UnsafeAndMeaningChangingMappingsFailBeforeTransport(string json) =>
        Assert.Throws<ArgumentException>(() => SourceMapping.Load(json));

    [Fact]
    public void RequiredMissingColumnRefusesWhileOptionalMetadataIsRetainedAndCaseResolves()
    {
        var mapping = SourceMapping.Load();
        var actual = mapping.Tables["Payroll"].Fields.Values.Select(f => f.Column).ToList();
        actual.Remove("HourlyRate");
        actual.Remove("AccountId");
        actual.Add("Accountid");
        actual.Add("Extra");
        var resolution = mapping.Resolve("Payroll", actual);
        Assert.Empty(resolution.MissingRequired);
        Assert.Contains("hourly_rate", resolution.MissingOptional);
        Assert.Contains("account_id", resolution.CaseDifferences);
        Assert.Contains("Extra", resolution.Extra);
        actual.Remove("Accountid");
        Assert.Contains("account_id", mapping.Resolve("Payroll", actual).MissingRequired);
    }

    [Fact]
    public void StreamingRowLimitStopsAtOneExtraRowAndDisposesTheEnumerator()
    {
        var (source, _, transport) = SourceTestData.Source(limit: 1);
        Assert.Throws<SourceTooLarge>(() => source.LoadPayPeriods(7));
        Assert.Equal(transport.Queries.Count, transport.DisposedStreams);
        Assert.True(transport.RowsSent < 10);
    }

    [Fact]
    public void OptionalTableAbsenceIsRecordedButAnOutageIsNeverAnEmptyPayroll()
    {
        var tables = SourceTestData.MiniTables();
        tables.Remove("PayFrequency");
        var (source, _, transport) = SourceTestData.Source(tables);
        Assert.Contains("PayFrequency", source.LoadProjection(7)!.MissingTables);
        transport.Failure = new SourceUnavailable();
        Assert.Throws<SourceUnavailable>(() => source.LoadPayPeriods(7));
    }

    [Fact]
    public void UnknownEmptyAndUnconfiguredAreDistinct()
    {
        var (source, _, transport) = SourceTestData.Source();
        Assert.Null(source.LoadProjection(999));
        Assert.Empty(source.LoadPayPeriods(999));
        var queries = transport.Queries.Count;
        Assert.Empty(source.LoadPayPeriods(null));
        Assert.Equal(queries, transport.Queries.Count);
        transport.IsConfigured = false;
        Assert.False(source.IsConfigured);
        Assert.Throws<SourceNotConfigured>(() => source.LoadProjection(7));
        var tables = SourceTestData.MiniTables();
        tables["Payroll"] = [];
        var empty = SourceTestData.Source(tables).Source.LoadProjection(7);
        Assert.NotNull(empty);
        Assert.Empty(empty.Rows);
    }

    [Fact]
    public void MetadataCacheIsInstanceScopedResettableAndDoesNotCacheAbsence()
    {
        var (source, scanner, transport) = SourceTestData.Source();
        _ = source.LoadPayPeriods(7);
        var count = transport.DiscoveryCalls;
        _ = source.LoadPayPeriods(8);
        Assert.Equal(count, transport.DiscoveryCalls);
        scanner.ClearCache();
        _ = source.LoadPayPeriods(8);
        Assert.True(transport.DiscoveryCalls > count);
        Assert.Equal("101", source.LoadPayPeriods(7)[0].Get("Employee_ID"));
        Assert.Equal("201", source.LoadPayPeriods(8)[0].Get("Employee_ID"));
        var other = SourceTestData.Source();
        _ = other.Source.LoadPayPeriods(7);
        Assert.True(other.Transport.DiscoveryCalls > 0);
    }

    [Theory]
    [InlineData("period_end", "worksite_then_location")]
    [InlineData("exclude", "worksite_then_location")]
    [InlineData("period_end", "worksite_only")]
    [InlineData("period_end", "location_only")]
    public void GroupedScopeAndFootprintAgreeWithProjectedPopulation(string dateMode, string siteMode)
    {
        var mapping = SourceMapping.Load("{\"transforms\":{\"null_pay_date\":\"" + dateMode
            + "\",\"worksite_location\":\"" + siteMode + "\"}}");
        var (source, _, transport) = SourceTestData.Source(mapping: mapping);
        var rows = source.LoadPayPeriods(7);
        var fromRows = SourceScope.FromRows(rows);
        var sql = source.PayrollScope(7);
        Assert.Equal(fromRows.TotalRows, sql.TotalRows);
        Assert.Equal(fromRows.TaxYears, sql.TaxYears);
        Assert.Equal(fromRows.States, sql.States);
        Assert.Equal(fromRows.PayDates, sql.PayDates);
        Assert.Equal(sql.States, source.Footprint()[7]);
        Assert.Single(transport.Queries, q => q.Kind == "scope");
        var statement = transport.Queries.Single(q => q.Kind == "scope");
        Assert.Contains("GROUP BY", statement.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("FORMAT(", statement.Sql, StringComparison.Ordinal);
        Assert.Equal(7L, statement.Parameters[0]);
    }

    [Theory]
    [InlineData("", true, "[dbo]")]
    [InlineData("dbo", false, "[dbo]")]
    [InlineData(null, false, "[tcc_source]")]
    public void BlankSchemaHasExplicitWarningAndSqlMetadataUsesDbo(string? schema, bool warning, string sqlSchema)
    {
        var (_, scanner, transport) = SourceTestData.Source();
        var selected = new SourceScanner(transport, scanner.Mapping, schema);
        Assert.Equal(warning, selected.HasBlankSchemaWarning);
        Assert.Contains(sqlSchema, selected.TableName("Payroll"), StringComparison.Ordinal);
    }
}
