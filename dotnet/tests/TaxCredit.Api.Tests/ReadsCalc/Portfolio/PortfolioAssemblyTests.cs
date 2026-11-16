using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

public sealed class PortfolioAssemblyTests
{
    [Fact]
    public async Task Portfolio_and_discovery_match_python_312_public_fixture()
    {
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        using var scope = host.App.Services.CreateScope();
        var portfolio = scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>();
        Assert.Equal(2025, portfolio.LatestTaxYear());
        PortfolioTestData.EqualFixture("portfolio", portfolio.BuildPortfolio(2025));
        var discovery = scope.ServiceProvider.GetRequiredService<ReadsDiscoveryService>();
        var recorder = new TrailRecorder("Pending");
        using (TrailContext.Use(recorder))
        {
            PortfolioTestData.EqualFixture("discovery", discovery.DiscoverCredits(["GA_JTC", "GA_JTC"], taxYear: 2025));
        }
        Assert.Contains(recorder.Steps, step => step.Step == "Scan rule library (statutory One/Zero engine)");
        Assert.Equal(3, recorder.Steps.Count(step => step.Step.StartsWith("Hit: ", StringComparison.Ordinal)));
        Assert.NotSame(portfolio, host.App.Services.GetRequiredService<ReadsPortfolioService>());
    }

    [Fact]
    public async Task Unknown_client_missing_payroll_and_unauthored_statute_do_not_become_successful_zeroes()
    {
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        using var scope = host.App.Services.CreateScope();
        var portfolio = scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>();
        Assert.Throws<ClientRunNotAvailable>(() => portfolio.BuildPortfolio(2025, accountId: 9999));
        Assert.Throws<PyFileNotFoundError>(() => portfolio.BuildPortfolio(1999));
        var trend = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>();
        Assert.Throws<ClientRunNotAvailable>(() => trend.Execute(new("ZZ")));
        Assert.Throws<ClientRunNotAvailable>(() => trend.Execute(new("GA", 9999)));
        Assert.Throws<ArgumentException>(() => trend.Execute(new("GA", Method: "minmax")));
    }

    [Fact]
    public async Task Source_and_fiscal_failures_propagate_instead_of_becoming_empty_views()
    {
        await using var host = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IPayrollSource>(new PortfolioPayroll(_ => throw new SourceUnavailable()));
        });
        using var scope = host.App.Services.CreateScope();
        Assert.Throws<SourceUnavailable>(() => scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>().BuildPortfolio(2025));
        Assert.Throws<SourceUnavailable>(() => scope.ServiceProvider.GetRequiredService<ReadsDiscoveryService>().DiscoverCredits());
        Assert.Throws<SourceUnavailable>(() => scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>().Execute(new("GA")));
    }

    [Fact]
    public async Task Stored_averages_price_without_a_payroll_read_and_an_explicit_program_cannot_change_state()
    {
        await using var host = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IPayrollSource>(new PortfolioPayroll(_ => throw new SourceUnavailable()));
        });
        using var scope = host.App.Services.CreateScope();
        var portfolio = scope.ServiceProvider.GetRequiredService<ReadsPortfolioService>();
        var result = portfolio.StateCredit("GA", 2025, currentAverage: 120.5, priorAverage: 100.25, programCode: "GA_JTC");
        Assert.Equal(18.25, result["qualifying_jobs"]);
        Assert.Equal("GA_JTC", result["credit_code"]);
        Assert.Equal(63875L, result["annual_credit_usd"]);
        Assert.Throws<ProgramStateConflict>(() =>
            portfolio.StateCredit("NY", 2025, currentAverage: 120.5, programCode: "GA_JTC"));
    }
}
