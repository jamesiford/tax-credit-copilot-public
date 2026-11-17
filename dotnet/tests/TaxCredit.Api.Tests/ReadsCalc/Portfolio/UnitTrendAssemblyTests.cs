using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

public sealed class UnitTrendAssemblyTests
{
    [Theory]
    [InlineData("min_max")]
    [InlineData("pay_period")]
    public async Task Complete_trend_matches_python_312_including_legacy_tiers_declines_and_money(string method)
    {
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        using var scope = host.App.Services.CreateScope();
        var trend = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>();
        PortfolioTestData.EqualFixture("trend-" + method, trend.Execute(new("GA", Method: method)));
        PortfolioTestData.EqualFixture("trend-" + method, trend.Execute(new("GA", Method: method)));
    }

    [Fact]
    public async Task Explicit_program_and_base_override_retain_program_and_unit_grain()
    {
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        using var scope = host.App.Services.CreateScope();
        var result = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>()
            .Execute(new("GA", BaseYear: 2025, ProgramCode: "GA_JTC"));
        Assert.Equal("GA_JTC", result["program_code"]);
        var units = ((List<object?>)result["units"]!).Cast<PyDict>().ToList();
        Assert.All(units, unit =>
        {
            Assert.Equal(2025L, unit["base_year"]);
            Assert.Equal("override", unit["base_year_source"]);
            var rows = ((List<object?>)unit["rows"]!).Cast<PyDict>().ToList();
            Assert.Equal("before_base", rows.Single(r => (long)r["tax_year"]! == 2024)["status"]);
            Assert.Equal("base", rows.Single(r => (long)r["tax_year"]! == 2025)["status"]);
        });
    }

    [Fact]
    public async Task A_new_scope_loads_fresh_source_and_never_reuses_another_queries_replay()
    {
        var calls = 0;
        await using var host = await TestHost.Start(services: PortfolioTestData.Register);
        IReadOnlyList<PayRow> rows;
        using (var original = host.App.Services.CreateScope())
        {
            rows = original.ServiceProvider.GetRequiredService<IPayrollSource>().LoadPayPeriods(null);
        }
        await using var isolated = await TestHost.Start(services: services =>
        {
            PortfolioTestData.Register(services);
            services.AddSingleton<IPayrollSource>(new PortfolioPayroll(_ => ++calls == 1 ? rows : throw new SourceUnavailable()));
        });
        using var scope = isolated.App.Services.CreateScope();
        var trend = scope.ServiceProvider.GetRequiredService<ReadsUnitTrendService>();
        Assert.NotNull(trend.Execute(new("GA")));
        Assert.Throws<SourceUnavailable>(() => trend.Execute(new("GA")));
        Assert.Equal(2, calls);
    }
}
