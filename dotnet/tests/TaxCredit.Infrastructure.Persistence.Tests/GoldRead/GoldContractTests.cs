using System.Globalization;
using System.Reflection;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.GoldRead;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldContractTests(GoldFixture fixture) : IClassFixture<GoldFixture>
{
    [Fact]
    public void Whole_surface_has_exactly_twenty_five_members_and_is_implemented()
    {
        var members = typeof(IGoldReadPort).GetMembers(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.MemberType is MemberTypes.Property || m is MethodInfo { IsSpecialName: false }).ToArray();
        Assert.Equal(25, members.Length);
        var mapping = typeof(GoldReader).GetInterfaceMap(typeof(IGoldReadPort));
        Assert.Equal(25, mapping.TargetMethods.Length);
        Assert.All(mapping.TargetMethods, m => Assert.Equal(typeof(GoldReader), m.DeclaringType));
        Assert.Equal(7, fixture.Load.TableCounts.Keys.Count(k => k.StartsWith("gold/", StringComparison.Ordinal)));
    }

    [Theory]
    [InlineData("p1_reads", "ok.api-v2-clients-client-id-units", 2025, "min_max", 3, 0)]
    [InlineData("p1_query_edges", "units.limit-1", null, "min_max", 1, 0)]
    [InlineData("p1_query_edges", "units.offset-past-end", null, "min_max", 25, 99999)]
    [InlineData("p1_query_edges", "units.year-none", 1999, "min_max", 25, 0)]
    [InlineData("p1_query_edges", "units.method-pp", null, "pay_period", 25, 0)]
    public void Grid_matches_recorded_Python_fields(string recording, string id, int? year, string method, int limit, int offset)
    {
        var expected = fixture.Recording(recording, id).GetProperty("response").GetProperty("body").GetProperty("value");
        var actual = fixture.Reader.UnitPage(1001, method, year, limit: limit, offset: offset);
        foreach (var key in new[] { "items", "total", "months", "installments", "unit_totals" })
        {
            GoldAssert.Same(expected.GetProperty(key), actual[key]);
        }
        // The grid deliberately reports a successful zero-row sweep as calculated; drawers additionally test year coverage.
        var envelope = RunEnvelope.Create(GoldAssert.Row(actual, "run"), actual["in_flight"] as IReadOnlyDictionary<string, object?>);
        foreach (var key in envelope.Keys)
        {
            GoldAssert.Same(expected.GetProperty(key), envelope[key]);
        }
    }

    [Fact]
    public void Unit_drawer_matches_recording_and_keeps_all_unit_columns()
    {
        var expected = fixture.Recording("p1_reads", "boot.unit").GetProperty("response").GetProperty("body").GetProperty("value");
        var actual = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max", new UnitDrillOptions { Limit = 2 });
        GoldAssert.Same(expected.GetProperty("unit"), actual["unit"]);
        GoldAssert.Same(expected.GetProperty("months"), actual["months"]);
        // HTTP adds presentation-only fields to each cohort. Every stored field must still agree.
        foreach (var cohort in new[] { "employees", "near_threshold" })
        {
            var rows = GoldAssert.Rows(actual, cohort);
            var recorded = expected.GetProperty(cohort).EnumerateArray().ToArray();
            Assert.Equal(recorded.Length, rows.Count);
            for (var i = 0; i < rows.Count; i++)
            {
                foreach (var pair in rows[i])
                {
                    GoldAssert.Same(recorded[i].GetProperty(pair.Key), pair.Value);
                }
            }
        }
        Assert.Equal(34, GoldAssert.Row(actual, "unit").Count);
        Assert.IsType<bool>(GoldAssert.Row(actual, "unit")["qualified"]);
        Assert.IsType<double>(GoldAssert.Row(actual, "unit")["high_water_mark"]);
        Assert.Equal("3500.0", GoldAssert.Row(actual, "unit")["per_job_usd"]);
    }

    [Theory]
    [InlineData("p1_reads", "ok.api-eligibility-tax-year", 50, 0)]
    [InlineData("p1_query_edges", "eligibility.limit-1", 1, 1)]
    public void Eligibility_pivot_matches_certified_recording(string recording, string id, int limit, int offset)
    {
        var expected = fixture.Recording(recording, id).GetProperty("response").GetProperty("body").GetProperty("value");
        var actual = fixture.Reader.EligibilityPopulation(1001, 2025, 35, 680, new EligibilityOptions { Limit = limit, Offset = offset });
        var summary = GoldAssert.Row(actual, "summary");
        foreach (var key in new[] { "employees_evaluated", "min_max_eligible", "pay_period_eligible", "near_floor" })
        {
            GoldAssert.Same(expected.GetProperty(key), summary[key]);
        }
        GoldAssert.Same(expected.GetProperty("total"), actual["matching"]);
        var recorded = expected.GetProperty("rows").EnumerateArray().ToArray();
        var rows = GoldAssert.Rows(actual, "rows");
        Assert.Equal(recorded.Length, rows.Count);
        for (var i = 0; i < rows.Count; i++)
        {
            GoldAssert.Same(recorded[i].GetProperty("employee_id"), rows[i]["employee_id"]);
            GoldAssert.Same(recorded[i].GetProperty("record_token"), rows[i]["record_token"]);
            GoldAssert.Same(recorded[i].GetProperty("status"), rows[i]["status"]);
            foreach (var (prefix, field) in new[] { ("mm", "min_max"), ("pp", "pay_period") })
            {
                var method = recorded[i].GetProperty(field);
                GoldAssert.Same(method.GetProperty("weeks"), rows[i][prefix + "_weeks"]);
                GoldAssert.Same(method.GetProperty("avg_hours"), rows[i][prefix + "_hours"]);
                GoldAssert.Same(method.GetProperty("avg_wages"), rows[i][prefix + "_wages"]);
                GoldAssert.Same(method.GetProperty("eligible"), Convert.ToInt32(rows[i][prefix + "_eligible"], CultureInfo.InvariantCulture) != 0);
            }
        }
    }

    [Fact]
    public void Matrix_and_method_summary_match_recorded_read_without_engine()
    {
        var expected = fixture.Recording("p1_reads", "ok.api-onezero-matrix-tax-year").GetProperty("response").GetProperty("body").GetProperty("value");
        var actual = fixture.Reader.OnezeroMatrix(1001, 2025, "min_max");
        var summary = GoldAssert.Row(actual, "summary");
        foreach (var key in new[] { "annual_average", "eligible_employees", "matrix_rows", "contested_months" })
        {
            GoldAssert.Same(expected.GetProperty(key), summary[key]);
        }
        var units = GoldAssert.Rows(actual, "units").Select(row => new
        {
            unit_id = row["worksite_id"],
            fein = row["entity_fein"],
            month_totals = Enumerable.Range(1, 12).Select(i => row[$"month_{i:00}"]).ToArray(),
            total = row["total"],
            average_headcount = row["average_headcount"],
        }).ToArray();
        GoldAssert.Same(expected.GetProperty("summary"), units);
        var recorded = expected.GetProperty("matrix").EnumerateArray().ToArray();
        var rows = GoldAssert.Rows(actual, "matrix");
        Assert.Equal(recorded.Length, rows.Count);
        for (var i = 0; i < rows.Count; i++)
        {
            foreach (var key in new[] { "employee_id", "record_token", "weight" })
            {
                GoldAssert.Same(recorded[i].GetProperty(key), rows[i][key]);
            }
            GoldAssert.Same(recorded[i].GetProperty("unit_id"), rows[i]["worksite_id"]);
            GoldAssert.Same(recorded[i].GetProperty("fein"), rows[i]["entity_fein"]);
            GoldAssert.Same(recorded[i].GetProperty("months"), Enumerable.Range(1, 12).Select(m => rows[i][$"month_{m:00}"]).ToArray());
        }
    }
}
