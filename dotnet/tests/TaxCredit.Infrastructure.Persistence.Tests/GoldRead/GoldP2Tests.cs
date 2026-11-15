using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.GoldRead;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldRead;

public sealed class GoldP2Tests
{
    [Fact]
    [Trait("Category", "heavy")]
    public void P2_seed_reads_match_recorded_multi_client_grid_and_eligibility()
    {
        using var fixture = new GoldFixture("P2");
        var expected = fixture.Recording("p2_reads_writes", "boot.unit").GetProperty("response").GetProperty("body").GetProperty("value");
        var page = fixture.Reader.UnitPage(2001, "min_max", 2025, limit: 2);
        foreach (var field in new[] { "items", "total", "months", "installments", "unit_totals" })
        {
            GoldAssert.Same(expected.GetProperty(field), page[field]);
        }
        var provenance = RunEnvelope.Create(GoldAssert.Row(page, "run"), null);
        foreach (var field in provenance.Keys)
        {
            GoldAssert.Same(expected.GetProperty(field), provenance[field]);
        }
        var population = fixture.Reader.EligibilityPopulation(2001, 2025, 35, 680, new EligibilityOptions { Limit = 3 });
        var recorded = fixture.Recording("p2_reads_writes", "client2001.eligibility").GetProperty("response").GetProperty("body").GetProperty("value");
        foreach (var field in new[] { "employees_evaluated", "min_max_eligible", "pay_period_eligible", "near_floor" })
        {
            GoldAssert.Same(recorded.GetProperty(field), GoldAssert.Row(population, "summary")[field]);
        }
        Assert.NotNull(fixture.Reader.LatestRun(2002));
        Assert.NotNull(fixture.Reader.LatestRun(2003));
        Assert.NotNull(fixture.Reader.LatestRun(2004));
        Assert.Null(fixture.Reader.LatestRun(1001));
    }
}
