using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.GoldRead;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldBehaviorTests(GoldFixture fixture) : IClassFixture<GoldFixture>
{
    [Fact]
    public void Risk_counts_cover_the_population_not_only_the_bounded_rows()
    {
        var run = Assert.IsAssignableFrom<IReadOnlyDictionary<string, object?>>(fixture.Reader.LatestRun(1001));
        var runId = Assert.IsType<string>(run["run_id"]);
        using var session = fixture.Database.Open();
        var population = session.Query(1001, "SELECT * FROM tcc_gold.employee_eligibility WHERE {tenant} " +
            "AND tax_year = ? AND method = ? AND run_id = ? AND avg_weekly_hours IS NOT NULL", 2025, "min_max", runId);
        var expectedRisk = population.Where(r => Num(r, "eligible") == 1 && (Num(r, "avg_weekly_hours") < 38.5 || Num(r, "avg_weekly_wages") < 748))
            .OrderBy(r => Num(r, "avg_weekly_hours")).Select(r => r["record_token"]).ToArray();
        var risk = fixture.Reader.AtRisk(1001, 2025, "min_max", new RiskOptions(35, 680));
        Assert.Equal(expectedRisk, GoldAssert.Rows(risk, "rows").Select(r => r["record_token"]));
        Assert.Equal(population.Count, Num(GoldAssert.Row(risk, "counts"), "evaluated"));
        var proximity = fixture.Reader.ProximityCandidates(1001, 2025, "min_max", new RiskOptions(35, 680, WidestBandHours: 2));
        Assert.Equal(population.Count(r => Num(r, "avg_weekly_hours") >= 33), GoldAssert.Rows(proximity, "rows").Count);
        var counts = GoldAssert.Row(proximity, "counts");
        Assert.Equal(population.Count, Num(counts, "evaluated"));
        Assert.Equal(population.Count(r => Num(r, "eligible") == 1), Num(counts, "eligible_count"));
        Assert.True(Num(counts, "eligible_count") > 1);
        Assert.Equal(population.Count(r => Num(r, "eligible") == 0 && Num(r, "avg_weekly_hours") < 35 && Num(r, "avg_weekly_wages") >= 680), Num(counts, "hours_only"));
    }

    [Fact]
    public void Employee_drill_resolves_stored_token_and_periods_without_re_minting()
    {
        var drawer = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max", new UnitDrillOptions { Limit = 2 });
        var token = Assert.IsType<string>(GoldAssert.Rows(drawer, "employees")[0]["record_token"]);
        var runId = Assert.IsType<string>(GoldAssert.Row(drawer, "run")["run_id"]);
        var drill = fixture.Reader.EmployeeDrill(1001, 2025, token);
        Assert.Equal(2, GoldAssert.Rows(drill, "verdicts").Count);
        Assert.NotEmpty(GoldAssert.Rows(drill, "segments"));
        Assert.NotEmpty(GoldAssert.Rows(drill, "periods"));
        var periods = fixture.Reader.CohortPeriods(1001, 2025, runId, [token, token, "", "missing"]);
        Assert.Single(periods);
        Assert.Equal(GoldAssert.Rows(drill, "periods").Count, periods[token].Count);
        var eligibility = fixture.Reader.Employee(token, 1001, 2025, runId);
        Assert.Equal(2, eligibility.Count);
        Assert.All(eligibility, row => Assert.Equal(token, row["record_token"]));
        Assert.NotEmpty(fixture.Reader.EmployeeUnits(token, 1001, 2025, runId, "min_max"));
        Assert.Empty(GoldAssert.Rows(fixture.Reader.EmployeeDrill(1002, 2025, token), "verdicts"));
        Assert.Empty(GoldAssert.Rows(fixture.Reader.EmployeeDrill(1001, 2024, token), "verdicts"));
        Assert.Empty(fixture.Reader.CohortPeriods(1001, 2025, runId, []));
    }

    [Fact]
    public void Independent_filters_preserve_cohort_totals_and_sort_before_limit()
    {
        var all = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max");
        var selected = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max", new UnitDrillOptions
        {
            Limit = 1,
            EmployeeFilters = "avg_weekly_hours:>=39",
            NearFilters = "avg_weekly_hours:>=33",
            Sort = "avg_weekly_hours",
            Order = "desc",
        });
        Assert.Single(GoldAssert.Rows(selected, "employees"));
        Assert.Single(GoldAssert.Rows(selected, "near_threshold"));
        Assert.Equal(GoldAssert.Rows(all, "employees").Count, selected["employees_total"]);
        Assert.Equal(GoldAssert.Rows(all, "near_threshold").Count, selected["near_total"]);
        var top = GoldAssert.Rows(all, "employees").Max(r => Num(r, "avg_weekly_hours"));
        Assert.Equal(top, Num(GoldAssert.Rows(selected, "employees")[0], "avg_weekly_hours"));
        var invalid = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max", new UnitDrillOptions { EmployeeFilters = "employee_id:~%" });
        Assert.Empty(GoldAssert.Rows(invalid, "employees"));
        Assert.Equal(GoldAssert.Rows(all, "near_threshold").Count, GoldAssert.Rows(invalid, "near_threshold").Count);
        var malformed = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 2025, "min_max", new UnitDrillOptions { EmployeeFilters = "bogus:>=1;avg_weekly_hours:no-number" });
        Assert.Equal(GoldAssert.Rows(all, "employees").Count, GoldAssert.Rows(malformed, "employees").Count);
    }

    [Fact]
    public void Month_filters_count_contributors_not_every_person_at_the_worksite()
    {
        var runId = Assert.IsType<string>(fixture.Reader.LatestRun(1001)!["run_id"]);
        var all = fixture.Reader.UnitEmployees(1001, "GA_ATL_HQ", 2025, "min_max", runId);
        var narrowed = fixture.Reader.UnitEmployees(1001, "GA_ATL_HQ", 2025, "min_max", runId, 3);
        Assert.Equal(all.Count(r => Num(r, "month_03") > 0), narrowed.Count);
        Assert.True(narrowed.Count < all.Count);
        Assert.All(narrowed, r => Assert.True(Num(r, "month_03") > 0));
        Assert.Throws<ArgumentOutOfRangeException>(() => fixture.Reader.UnitEmployees(1001, "GA_ATL_HQ", 2025, "min_max", runId, 0));
        Assert.Throws<ArgumentOutOfRangeException>(() => fixture.Reader.UnitEmployees(1001, "GA_ATL_HQ", 2025, "min_max", runId, 13));
    }

    [Fact]
    public void Eligibility_filters_do_not_change_population_or_recorded_verdict()
    {
        var all = fixture.Reader.EligibilityPopulation(1001, 2025, 35, 680);
        var filtered = fixture.Reader.EligibilityPopulation(1001, 2025, 35, 680,
            new EligibilityOptions { Status = "both", Limit = 1, Sort = "total_hours", Order = "desc" });
        GoldAssert.Same(GoldAssert.Json(all["summary"]), filtered["summary"]);
        Assert.Single(GoldAssert.Rows(filtered, "rows"));
        Assert.Equal(Num(GoldAssert.Row(all, "summary"), "eligible_both"), Convert.ToDouble(filtered["matching"], CultureInfo.InvariantCulture));
        var moved = fixture.Reader.EligibilityPopulation(1001, 2025, 100, 10000);
        Assert.Equal(GoldAssert.Row(all, "summary")["min_max_eligible"], GoldAssert.Row(moved, "summary")["min_max_eligible"]);
        Assert.True(Num(GoldAssert.Row(moved, "summary"), "verdict_disagreements") > 0);
        Assert.Empty(GoldAssert.Rows(fixture.Reader.EligibilityPopulation(1001, 2025, 35, 680, new EligibilityOptions { Q = "%" }), "rows"));
    }

    [Fact]
    public void Absent_year_unknown_unit_and_missing_client_are_distinct()
    {
        Assert.NotNull(fixture.Reader.LatestRun(1001, "GA_JTC"));
        Assert.Null(fixture.Reader.LatestRun(1001, "UNKNOWN"));
        var absent = fixture.Reader.UnitDrill(1001, "GA_ATL_HQ", 1999, "min_max");
        Assert.Equal(false, absent["year_held"]);
        Assert.Null(absent["run"]);
        var unknown = fixture.Reader.UnitDrill(1001, "does-not-exist", 2025, "min_max");
        Assert.Equal(true, unknown["year_held"]);
        Assert.NotNull(unknown["run"]);
        Assert.Null(unknown["unit"]);
        Assert.Null(fixture.Reader.LatestRun(999999));
        Assert.Null(fixture.Reader.Unit(999999, "GA_ATL_HQ", 2025, "min_max"));
        Assert.Null(fixture.Reader.UnitPage(999999, "min_max")["run"]);
        Assert.Null(fixture.Reader.EligibilityPopulation(1001, 1999, 35, 680)["summary"]);
        Assert.Null(fixture.Reader.OnezeroMatrix(1001, 1999, "min_max")["summary"]);
        var envelope = RunEnvelope.Create(fixture.Reader.LatestRun(1001), null, false);
        Assert.Equal("not_calculated", envelope["calculation_state"]);
        Assert.NotNull(envelope["run"]);
    }

    [Fact]
    public void Series_uses_recorded_measuring_dates_and_every_reached_year()
    {
        var series = fixture.Reader.HeadcountSeries(1001, 2025, "min_max");
        Assert.Equal(12, Assert.IsType<double[]>(series["months"]).Length);
        Assert.Equal(12, Assert.IsAssignableFrom<IReadOnlyList<string>>(series["month_ends"]).Count);
        Assert.NotNull(series["annual_average"]);
        var years = fixture.Reader.ClientYearSeries(1001);
        Assert.NotEmpty(GoldAssert.Rows(years, "years"));
        Assert.Null(fixture.Reader.HeadcountSeries(999999, 2025, "min_max")["annual_average"]);
        Assert.Empty(Assert.IsAssignableFrom<Array>(fixture.Reader.ClientYearSeries(999999)["years"]));
        Assert.NotEmpty(fixture.Reader.Installments(1001, "min_max"));
        Assert.NotEmpty(fixture.Reader.CreditColumns(1001, "min_max"));
        var totals = fixture.Reader.UnitTotals(1001, "min_max");
        Assert.All(totals, r => Assert.IsType<string>(r["total_annual_credit_usd"]));
        using var outer = fixture.Reader.Scope();
        using (fixture.Reader.Scope())
        {
            Assert.NotNull(fixture.Reader.LatestRun(1001));
        }
        Assert.NotNull(fixture.Reader.LatestRun(1001));
        Assert.Equal(1, fixture.Reader.Connection.Keepalive());
        Assert.Equal(2, fixture.Reader.Connection.Prewarm(2));
    }

    [Fact]
    public void Whole_grid_joins_months_to_the_row_run_not_the_latest_manifest_of_any_program()
    {
        var unit = Assert.Single(fixture.Reader.UnitYears(1001, "min_max", limit: 1).Items);
        var site = Assert.IsType<string>(unit["worksite_id"]);
        var year = Convert.ToInt32(unit["tax_year"], CultureInfo.InvariantCulture);
        var originalRun = Assert.IsType<string>(unit["run_id"]);
        using var session = fixture.Database.Open();
        foreach (var table in new[] { "unit_year_master", "unit_month_summary" })
        {
            session.Execute(1001, "UPDATE tcc_gold." + table + " SET run_id = ? WHERE {tenant} AND worksite_id = ? AND tax_year = ? AND method = ?",
                "row-owned-run", site, year, "min_max");
        }
        try
        {
            var page = fixture.Reader.UnitPage(1001, "min_max", limit: 1);
            Assert.Equal("row-owned-run", Assert.Single(GoldAssert.Rows(page, "months"))["run_id"]);
            Assert.Equal(originalRun, GoldAssert.Row(page, "run")["run_id"]);
        }
        finally
        {
            foreach (var table in new[] { "unit_year_master", "unit_month_summary" })
            {
                session.Execute(1001, "UPDATE tcc_gold." + table + " SET run_id = ? WHERE {tenant} AND worksite_id = ? AND tax_year = ? AND method = ?",
                    originalRun, site, year, "min_max");
            }
        }
    }

    private static double Num(IReadOnlyDictionary<string, object?> row, string key) =>
        row[key] is null ? 0 : Convert.ToDouble(row[key], CultureInfo.InvariantCulture);
}
