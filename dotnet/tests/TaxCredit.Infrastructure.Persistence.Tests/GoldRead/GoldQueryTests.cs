using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.GoldRead;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldQueryTests(GoldFixture fixture) : IClassFixture<GoldFixture>
{
    [Fact]
    public void Catalogue_names_all_seven_gold_tables_and_manifest_with_blocked_identity()
    {
        var service = new GoldDataQuery(fixture.Database);
        var catalog = service.Catalog();
        Assert.Equal(8, catalog.Count);
        Assert.Contains(catalog, d => d.Name == "run_manifest");
        Assert.All(catalog.Where(d => d.EmployeeLevel), d => Assert.Contains(d.Columns, c => c.Name == "employee_id" && c.Sensitivity == "blocked"));
        Assert.Contains(catalog.Single(d => d.Name == "run_manifest").Columns, c => c.Name == "triggered_by" && c.Sensitivity == "blocked");
        Assert.Equal(32, catalog.Single(d => d.Name == "unit_year_master").Columns.Count);
    }

    [Fact]
    public void Structured_credit_query_matches_exact_unit_totals_and_separates_methods()
    {
        var service = new GoldDataQuery(fixture.Database);
        var query = service.Run(new GoldQuerySpec
        {
            Dataset = "unit_year_master",
            ClientId = 1001,
            Select = ["worksite_id"],
            GroupBy = ["worksite_id"],
            Measures = [new("annual_credit_usd", "sum", "identified")],
            Method = "min_max",
        });
        Assert.False(query.EmployeeLevel);
        Assert.False(query.Truncated);
        Assert.Equal(new[] { "method", "worksite_id", "identified" }, query.Columns);
        var totals = fixture.Reader.UnitTotals(1001, "min_max");
        Assert.Equal(totals.Count, query.Rows.Count);
        for (var i = 0; i < query.Rows.Count; i++)
        {
            Assert.Equal(totals[i]["worksite_id"], query.Rows[i]["worksite_id"]);
            Assert.Equal(totals[i]["total_annual_credit_usd"], query.Rows[i]["identified"]);
        }
        var both = service.Run(new GoldQuerySpec
        {
            Dataset = "employee_eligibility",
            ClientId = 1001,
            Measures = [new("*", "count")],
        });
        Assert.Equal(2, both.Rows.Count);
        Assert.Equal(new[] { "min_max", "pay_period" }, both.Rows.Select(r => r["method"]));
    }

    [Theory]
    [InlineData("unit_year_master; DROP TABLE tcc_gold.unit_year_master", "average_headcount", "unknown_dataset")]
    [InlineData("unit_year_master", "annual_credit_usd) FROM tcc_gold.unit_year_master--", "unknown_column")]
    [InlineData("employee_eligibility", "employee_id", "blocked_column")]
    [InlineData("run_manifest", "triggered_by", "blocked_column")]
    public void Unreviewed_SQL_and_blocked_columns_never_reach_execution(string dataset, string column, string code)
    {
        var service = new GoldDataQuery(fixture.Database);
        var error = Assert.Throws<GoldQueryException>(() => service.Run(new GoldQuerySpec
        {
            Dataset = dataset,
            ClientId = 1001,
            Select = [column],
        }));
        Assert.Equal(code, error.Code);
    }

    [Fact]
    public void Every_label_order_filter_and_group_is_validated_before_execution()
    {
        var service = new GoldDataQuery(fixture.Database);
        var baseQuery = new GoldQuerySpec { Dataset = "unit_year_master", ClientId = 1001, Select = ["worksite_id"] };
        Assert.Equal("malformed_spec", Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { ClientId = 0 })).Code);
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Limit = 501 }));
        Assert.Equal("duplicate_label", Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Select = ["worksite_id", "worksite_id"] })).Code);
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { GroupBy = ["employee_id"] }));
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { OrderBy = [new("worksite_id;DELETE", "asc")] }));
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Measures = [new("annual_credit_usd", "sum", "x;DELETE")], GroupBy = ["worksite_id"] }));
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Filters = [new("worksite_id", "contains", "%")] }));
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Filters = [new("tax_year", "gte", double.NaN)] }));
        Assert.Throws<GoldQueryException>(() => service.Run(baseQuery with { Filters = [new("tax_year", "in", Enumerable.Range(2000, 51).ToArray())] }));
        var injectedValue = service.Run(baseQuery with { Filters = [new("worksite_id", "eq", "' OR 1=1 --")] });
        Assert.Empty(injectedValue.Rows);
    }

    [Fact]
    public void Read_caps_probe_truncation_and_employee_audience_cannot_be_selected_by_the_specification()
    {
        var service = new GoldDataQuery(fixture.Database);
        var capped = service.Run(new GoldQuerySpec { Dataset = "unit_year_master", ClientId = 1001, Select = ["worksite_id", "tax_year"], Limit = 1 });
        Assert.True(capped.Truncated);
        Assert.Single(capped.Rows);
        var employee = new GoldQuerySpec { Dataset = "employee_eligibility", ClientId = 1001, Select = ["record_token", "avg_weekly_hours"], Limit = 1 };
        Assert.Equal("employee_level_not_allowed", Assert.Throws<GoldQueryException>(() => service.Run(employee)).Code);
        Assert.Equal("employee_level_not_allowed", Assert.Throws<GoldQueryException>(() => service.Run(employee with { Select = ["tax_year", "weeks_worked"] })).Code);
        var firstParty = new GoldDataQuery(fixture.Database, id => id == 1001).Run(employee);
        Assert.True(firstParty.EmployeeLevel);
        Assert.Single(firstParty.Rows);
        Assert.Throws<GoldQueryException>(() => service.DistinctValues(1001, "employee_eligibility", "record_token"));
        var categories = service.DistinctValues(1001, "unit_year_master", "worksite_id", limit: 1);
        Assert.True(categories.Truncated);
        Assert.Single(categories.Rows);
        Assert.Equal("GA_ATL_HQ", categories.Rows[0]["value"]);
    }

    [Fact]
    public void Exact_money_sums_preserve_four_decimal_lexemes_above_double_integer_precision()
    {
        const long client = 910001;
        using var session = fixture.Database.Open();
        var original = session.Query(1001, "SELECT * FROM tcc_gold.unit_year_master WHERE {tenant} AND method = ? AND tax_year = ?", "min_max", 2025)[0];
        var columns = original.Keys.ToArray();
        var first = original.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
        first["client_id"] = client;
        first["worksite_id"] = "EXACT";
        first["tax_year"] = 2030L;
        first["annual_credit_usd"] = "99999999999999.9999";
        var second = new Dictionary<string, object?>(first, StringComparer.Ordinal)
        {
            ["tax_year"] = 2031L,
            ["annual_credit_usd"] = "0.0001",
        };
        session.Insert(client, "tcc_gold.unit_year_master", columns,
            [columns.Select(c => first[c]).ToArray(), columns.Select(c => second[c]).ToArray()]);
        try
        {
            Assert.Equal("100000000000000.0000", Assert.Single(fixture.Reader.UnitTotals(client, "min_max"))["total_annual_credit_usd"]);
            var result = new GoldDataQuery(fixture.Database).Run(new GoldQuerySpec
            {
                Dataset = "unit_year_master",
                ClientId = client,
                Method = "min_max",
                Measures = [new("annual_credit_usd", "sum", "eligible")],
            });
            Assert.Equal("100000000000000.0000", Assert.Single(result.Rows)["eligible"]);
            Assert.All(fixture.Reader.UnitYears(client, "min_max").Items, r => Assert.IsType<string>(r["annual_credit_usd"]));
            session.Execute(client, "UPDATE tcc_gold.unit_year_master SET annual_credit_usd = NULL WHERE {tenant}");
            Assert.Null(Assert.Single(fixture.Reader.UnitTotals(client, "min_max"))["total_annual_credit_usd"]);
            var unknownAmount = new GoldDataQuery(fixture.Database).Run(new GoldQuerySpec
            {
                Dataset = "unit_year_master",
                ClientId = client,
                Method = "min_max",
                Measures = [new("annual_credit_usd", "sum", "credit")],
            });
            Assert.Null(Assert.Single(unknownAmount.Rows)["credit"]);
        }
        finally
        {
            session.Execute(client, "DELETE FROM tcc_gold.unit_year_master WHERE {tenant}");
        }
    }
}
