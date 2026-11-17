using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

public sealed class PortfolioP2Tests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Staged_P2_source_fiscal_assembly_matches_the_accepted_python_seed_for_both_methods()
    {
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        host.Client.Timeout = TimeSpan.FromMinutes(5);
        await RuntimeRequests.Reset(host, "P2");
        using var scope = host.App.Services.CreateScope();
        var trend = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>();
        var gold = scope.ServiceProvider.GetRequiredService<IGoldReadPort>();
        var briefs = scope.ServiceProvider.GetRequiredService<ReadsStoredPortfolioBriefs>();
        foreach (var method in new[] { "min_max", "pay_period" })
        {
            var assembled = trend.Execute(new("GA", 2001, method, ProgramCode: "GA_JTC"));
            PortfolioTestData.EqualFixture("p2-trend-" + method, assembled);
            var stored = gold.HeadcountSeries(2001, 2025, method, "GA_JTC");
            var context = briefs.ClientContext(2001, 2025, method, "GA_JTC");
            Assert.Equal(true, context["calculated"]);
            Assert.Equal(stored["annual_average"], context["current_average"]);
        }
    }
}
