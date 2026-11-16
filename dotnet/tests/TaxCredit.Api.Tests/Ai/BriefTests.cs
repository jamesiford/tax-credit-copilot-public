using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Api.Tests.Ai;

public sealed class BriefTests
{
    [Fact]
    public void Portfolio_keeps_unavailable_and_unassessed_separate_without_reordering_the_book()
    {
        var brief = PortfolioBrief.Build(JsonNode.Parse("""
            {"total_clients":4,"assessed_clients":2,"items":[
              {"client_name":"Example North","priority_band":"on_the_line","jobs_margin":-0.83,"program_code":"GA_JTC","tax_year":2022},
              {"client_name":"Example West","priority_band":"declining","trend":{"fallen_by":47.7,"peak_tax_year":2022,"below_base":true,"credit_earned_usd":"97000"}},
              {"client_name":"Example Unavailable","data_unavailable":true}
            ]}
            """)!.AsObject());
        Assert.Equal("4 clients in the book, 2 assessed.", brief.Headline);
        Assert.Equal("1. Example North: On the line (GA_JTC TY2022), 0.83 jobs short of the minimum", brief.Facts[1]);
        Assert.Contains("down 47.7 jobs since TY2022, now below its base year, $97,000 already earned", brief.Facts[2], StringComparison.Ordinal);
        Assert.Contains(brief.Facts, f => f.Contains("are not ranked", StringComparison.Ordinal));
        Assert.Contains(brief.Caveats, c => c.Contains("have not been assessed", StringComparison.Ordinal));
        Assert.Equal(2, brief.Data["clients"]!.AsArray().Count);
    }

    [Fact]
    public void Client_distinguishes_finished_qualification_from_open_year_pace_and_preserves_rounding()
    {
        var brief = ClientBrief.Build(JsonNode.Parse("""
            {"items":[
              {"worksite_id":"UNIT-A","tax_year":2020,"status":"base","is_base_year":true},
              {"worksite_id":"UNIT-A","tax_year":2025,"status":"below_minimum","net_new_vs_base":0.34},
              {"worksite_id":"UNIT-A","tax_year":2026,"status":"in_progress","net_new_vs_base":0,"months_reachable":7},
              {"worksite_id":"UNIT-B","tax_year":2020,"status":"base","is_base_year":true},
              {"worksite_id":"UNIT-B","tax_year":2025,"status":"above_minimum","net_new_vs_base":12.9,"qualified":true},
              {"worksite_id":"UNIT-B","tax_year":2026,"status":"in_progress","net_new_vs_base":9.6,"months_reachable":7,"qualified":true}
            ],"unit_totals":[{"total_annual_credit_usd":"548730","total_tranche_lifetime_usd":"766290"}]}
            """)!.AsObject(), "Example Client", [2026]);
        Assert.Equal("2 locations; in its latest finished year, 1 qualify and 1 are below the minimum.", brief.Headline);
        Assert.Equal("$548,730 claimable across TY2020\u2013TY2025; $766,290 if maintained.", brief.Facts[1]);
        Assert.Contains("UNIT-A was below the minimum in TY2025 (0.3 net-new jobs against its TY2020 base).", brief.Facts);
        Assert.Contains("TY2026 is still open: 1 of 2 locations on track so far.", brief.Facts);
        Assert.Contains(brief.Caveats, c => c.Contains("placeholder", StringComparison.Ordinal));
        Assert.Contains(brief.Caveats, c => c.Contains("forecast, not a qualification", StringComparison.Ordinal));
        Assert.Contains("not a zero", ClientBrief.Build(new JsonObject(), "Example Client").Headline, StringComparison.Ordinal);
    }

    [Fact]
    public void Unit_summary_uses_the_supplied_floor_and_canonical_lever_not_an_hours_gap()
    {
        var brief = UnitBrief.Build(JsonNode.Parse("""
            {"year":2026,"unit":{"worksite_id":"UNIT-A","average_headcount":3,"base_average_headcount":7.33,
                "months_reachable":7,"status":"in_progress","qualified":false,"net_new_vs_base":0,"threshold":2},
             "thresholds":{"min_weekly_hours":35},"total_unfiltered":5,
             "near_threshold":[{"employee_id":"SYNTHETIC-A","avg_weekly_hours":36.33,"additional_weekly_hours":5.44},
                               {"employee_id":"SYNTHETIC-B","avg_weekly_hours":20}]}
            """)!.AsObject(), "Example Client", month: 7, placeholder: true);
        Assert.Equal("UNIT-A: 5 employees counted in July TY2026.", brief.Headline);
        Assert.Contains("1 more employees are within 5 hrs/week of the 35-hour floor; 2 are ineligible in all.", brief.Facts);
        Assert.Contains("Employee SYNTHETIC-A averages 36.33 hrs/week and needs 5.44 more to qualify.", brief.Facts);
        Assert.Equal(2, brief.Caveats.Count);
    }

    [Fact]
    public void Employee_summary_reads_both_recorded_verdicts_and_stored_month_positions()
    {
        var drill = JsonNode.Parse("""
            {"employee_id":"SYNTHETIC-A","tax_year":2026,
             "thresholds":{"minimum_average_weekly_hours":"35","minimum_average_weekly_wages_usd":"680"},
             "raw_source_rows":[{"selection_decision":"included"},{"selection_decision":"included"}],
             "step1":{"min_max":{"eligible":true,"avg_weekly_hours":42.7,"avg_weekly_wages":1032.54},
                      "pay_period":{"eligible":false,"avg_weekly_hours":30,"avg_weekly_wages":700}},
             "onezero":{"months":[1,2,3],"min_max":[{"unit_id":"UNIT-A","months":[0,1,1]}]}}
            """)!.AsObject();
        var brief = EmployeeBrief.Build(drill);
        Assert.Equal("Employee SYNTHETIC-A, TY2026: 2 pay periods on record, 2 included.", brief.Headline);
        Assert.Equal("Min-Max: eligible \u2014 42.70 hrs/week against 35, $1,033/week against $680.", brief.Facts[1]);
        Assert.StartsWith("Pay Period: not eligible", brief.Facts[2], StringComparison.Ordinal);
        Assert.Equal("Counted in 2 of 3 measuring months under Min-Max, at UNIT-A.", brief.Facts[3]);
    }

    [Theory]
    [InlineData("client", "a client summary needs client_id")]
    [InlineData("unit", "a unit summary needs client_id")]
    [InlineData("employee", "a employee summary needs client_id")]
    public async Task Missing_scope_refuses_before_reading_any_facts(string page, string detail)
    {
        var builder = new PageBriefBuilder(new NoReads(), new Scope());
        var failure = await Assert.ThrowsAsync<AiFactException>(async () => await builder.BuildAsync(new(page), CancellationToken.None));
        Assert.Equal(detail, failure.Message);
    }

    private sealed class Scope : IPageScope
    {
        public string ClientName(long clientId) => "Example Client";
        public IReadOnlyList<int> PlaceholderYears(string state) => [];
    }

    private sealed class NoReads : IPageFactSource
    {
        public ValueTask<JsonObject> PortfolioAsync(CancellationToken cancellationToken) => throw new InvalidOperationException();
        public ValueTask<JsonObject> ClientAsync(SummaryQuery query, CancellationToken cancellationToken) => throw new InvalidOperationException();
        public ValueTask<JsonObject> UnitAsync(SummaryQuery query, CancellationToken cancellationToken) => throw new InvalidOperationException();
        public ValueTask<JsonObject> EmployeeAsync(SummaryQuery query, CancellationToken cancellationToken) => throw new InvalidOperationException();
    }
}
