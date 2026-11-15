using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class ProjectionTests
{
    [Fact]
    public void SmallSourceRowsAndControlsAgreeExactlyWithPython312()
    {
        var tables = SourceTestData.MiniTables();
        var (source, _, _) = SourceTestData.Source(tables);
        using var oracle = SourceTestData.Oracle("mini", new { tables, accounts = new long[] { 7, 8 } });
        foreach (var result in oracle.RootElement.EnumerateArray())
        {
            var projection = source.LoadProjection(result.GetProperty("account").GetInt64())!;
            var actual = PyJson.Dumps(projection.Rows.Select(r => r.Dict).ToList());
            Assert.True(JsonNode.DeepEquals(JsonNode.Parse(actual), JsonNode.Parse(result.GetProperty("projected").GetRawText())));
            AssertControls(projection.Controls, result.GetProperty("controls"));
        }
    }

    [Theory]
    [InlineData("period_end", 2, 1, 0)]
    [InlineData("exclude", 1, 0, 1)]
    public void PayDatePolicyIsFlaggedAndNeverPretrimsFiscalWindow(string mode, int rows, int imputed, int excluded)
    {
        var mapping = SourceMapping.Load("{\"transforms\":{\"null_pay_date\":\"" + mode + "\"}}");
        var (source, _, _) = SourceTestData.Source(mapping: mapping);
        var result = source.LoadProjection(7)!;
        Assert.Equal(rows, result.Rows.Count);
        Assert.Equal(imputed, result.Controls.ImputedPayDates);
        Assert.Equal(excluded, result.Controls.ExcludedPayDates);
        Assert.All(result.Rows, r => Assert.Equal(2024L, r.Get("Tax_Year")));
        Assert.Equal("biweekly", result.Rows[0].Get("Pay_Frequency"));
        Assert.Equal(77L, result.Rows[0].Get("_Source_Pay_Frequency_Id"));
    }

    [Theory]
    [InlineData("worksite_then_location", "SC_site")]
    [InlineData("location_only", "SC_site")]
    [InlineData("worksite_only", "None")]
    public void WorksiteModesPreserveDanglingIdsAndStatePrefixes(string mode, string expected)
    {
        var mapping = SourceMapping.Load("{\"transforms\":{\"worksite_location\":\"" + mode + "\"}}");
        var (source, _, _) = SourceTestData.Source(mapping: mapping);
        Assert.Equal(expected, source.LoadPayPeriods(7)[0].Get("Worksite_ID"));
        Assert.Equal("GA_existing", source.LoadPayPeriods(8)[0].Get("Worksite_ID"));
    }

    [Fact]
    public void JunkNullNumbersAndAbsentSpansAreCountedNotStatutorilyFiltered()
    {
        var tables = SourceTestData.MiniTables();
        var row = (Dictionary<string, object?>)tables["Payroll"][0];
        row["Hours"] = "n/a";
        row["Wages"] = null;
        var second = (Dictionary<string, object?>)tables["Payroll"][1];
        second["PayPeriodStart"] = null;
        var result = SourceTestData.Source(tables).Source.LoadProjection(7)!;
        Assert.Single(result.Rows);
        Assert.Equal(1, result.Controls.DroppedNoSpan);
        Assert.Equal(1, result.Controls.NullHoursCoerced);
        Assert.Equal(1, result.Controls.NullWagesCoerced);
        Assert.Equal(0.0, result.Rows[0].Get("Hours_Worked"));
        Assert.Equal(0.0, result.Rows[0].Get("Gross_Wages"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(999L)]
    public void MissingAndDanglingPayCodesDefaultFlaggedWithoutDroppingRows(long? code)
    {
        var tables = SourceTestData.MiniTables();
        ((Dictionary<string, object?>)tables["Payroll"][0])["PayCodeId"] = code;
        var result = SourceTestData.Source(tables).Source.LoadProjection(7)!;
        Assert.Equal(2, result.Rows.Count);
        Assert.Equal(1, result.Controls.DefaultedCodeRows);
        Assert.True((bool)result.Rows[0].Get("_Pay_Code_Defaulted")!);
        Assert.Equal("Regular", result.Rows[0].Get("Pay_Code"));
    }

    [Theory]
    [InlineData("NaN")]
    [InlineData("Infinity")]
    [InlineData("1e999")]
    public void NonFinitePayrollIsAnExplicitCertifiedModelLimit(string value)
    {
        var tables = SourceTestData.MiniTables();
        ((Dictionary<string, object?>)tables["Payroll"][0])["Hours"] = value;
        var error = Assert.Throws<SourceFailureException>(() => SourceTestData.Source(tables).Source.LoadProjection(7));
        Assert.Equal("unsupported_nonfinite_payroll", error.Code);
        Assert.DoesNotContain(value, error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(1, "daily")]
    [InlineData(7, "weekly")]
    [InlineData(14, "biweekly")]
    [InlineData(16, "semimonthly")]
    [InlineData(30, "monthly")]
    [InlineData(45, "45d")]
    public void FrequencyUsesActualSpanNotForeignKey(int days, string expected) =>
        Assert.Equal(expected, PayrollProjector.FrequencyLabel(new DateOnly(2024, 1, 1), new DateOnly(2024, 1, 1).AddDays(days - 1)));

    internal static void AssertControls(ProjectionControls actual, JsonElement expected)
    {
        Assert.Equal(expected.GetProperty("payroll_rows_in").GetInt64(), actual.PayrollRowsIn);
        Assert.Equal(expected.GetProperty("bcs_rows_out").GetInt64(), actual.RowsOut);
        Assert.Equal(expected.GetProperty("dropped_no_period_span").GetInt64(), actual.DroppedNoSpan);
        Assert.Equal(expected.GetProperty("null_pay_date_imputed").GetInt64(), actual.ImputedPayDates);
        Assert.Equal(expected.GetProperty("null_pay_date_excluded").GetInt64(), actual.ExcludedPayDates);
        Assert.Equal(expected.GetProperty("null_hours_coerced_to_zero").GetInt64(), actual.NullHoursCoerced);
        Assert.Equal(expected.GetProperty("null_wages_coerced_to_zero").GetInt64(), actual.NullWagesCoerced);
        Assert.Equal(expected.GetProperty("worksite_fell_back_to_location").GetInt64(), actual.WorksiteFallbacks);
        Assert.Equal(expected.GetProperty("rows_with_no_county").GetInt64(), actual.RowsWithoutCounty);
        Assert.Equal(expected.GetProperty("distinct_employees").GetInt32(), actual.DistinctEmployees);
        Assert.Equal(expected.GetProperty("distinct_worksites").GetInt32(), actual.DistinctWorksites);
    }
}
