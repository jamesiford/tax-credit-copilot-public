using System.Reflection;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

public sealed class StoredPortfolioBriefTests
{
    [Fact]
    public async Task Stored_zero_is_calculated_and_a_missing_prior_is_named_without_reading_payroll()
    {
        var gold = Probe((name, args) => name switch
        {
            "Scope" => new ProbeScope(),
            "HeadcountSeries" => Map(("run", Map(("run_id", "accepted"), ("produced_at", "2026-01-01"))),
                ("annual_average", (int)args![1]! == 2025 ? 0.0 : null), ("month_ends", new[] { "2025-01-31" })),
            _ => throw new InvalidOperationException(name),
        });
        await using var host = await Start(gold);
        using var scope = host.App.Services.CreateScope();
        var views = scope.ServiceProvider.GetRequiredService<ReadsStoredPortfolioBriefs>();
        IReadOnlyDictionary<string, object?>? observed = null;
        var result = views.ClientContext(1001, 2025, programCode: "GA_JTC", onRun: run => observed = run);
        Assert.Equal(true, result["calculated"]);
        Assert.Equal(0.0, result["current_average"]);
        Assert.Equal(false, result["has_prior_year"]);
        Assert.Equal("accepted", observed!["run_id"]);
        Assert.Equal(false, views.ClientContext(1001, 2024)["calculated"]);
    }

    [Fact]
    public async Task Base_only_series_is_not_a_verdict_about_unheld_future_years()
    {
        var years = new[] { Map(("tax_year", 2023L), ("is_base_year", true), ("eligible_employees", 539L)) };
        var gold = Probe((name, _) => name == "ClientYearSeries" ? Map(("run", null), ("years", years)) : throw new InvalidOperationException(name));
        await using var host = await Start(gold);
        using var scope = host.App.Services.CreateScope();
        var result = scope.ServiceProvider.GetRequiredService<ReadsStoredPortfolioBriefs>().ClientTrend(1001, programCode: "GA_JTC");
        Assert.Equal(2023L, result["base_tax_year"]);
        Assert.Equal(0L, result["years_after_base"]);
        Assert.Null(result["eligible_every_year_since_base"]);
    }

    [Fact]
    public async Task At_risk_brief_uses_stored_eligible_population_and_fractional_jobs()
    {
        var rows = new[] { Map(("employee_id", "synthetic-person"), ("record_token", "stored-token"), ("weeks_worked", 52.0),
            ("total_hours", 1846.0), ("total_wages", 52000.0), ("avg_weekly_hours", 35.5), ("avg_weekly_wages", 1000.0), ("weight", 0.5)) };
        var gold = Probe((name, _) => name == "AtRisk"
            ? Map(("run", Map(("run_id", "accepted"))), ("counts", Map(("evaluated", 30L), ("eligible_count", 10L))), ("rows", rows))
            : throw new InvalidOperationException(name));
        await using var host = await Start(gold);
        using var scope = host.App.Services.CreateScope();
        var result = scope.ServiceProvider.GetRequiredService<ReadsStoredPortfolioBriefs>()
            .JobsAtRisk(scope.ServiceProvider.GetRequiredService<ClientRunResolver>(), 1001, "GA", 2023, programCode: "GA_JTC");
        Assert.Equal(true, result["calculated"]);
        Assert.Equal(30L, result["evaluated"]);
        Assert.Equal(10L, result["eligible"]);
        Assert.Equal(0.5, result["jobs_at_risk"]);
        Assert.Equal(1L, result["within_band"]);
        var cohort = Assert.Single((List<object?>)result["cohort"]!);
        Assert.Equal("stored-token", Assert.IsType<PyDict>(cohort)["record_token"]);
    }

    private static Task<TestHost> Start(IGoldReadPort gold) => TestHost.Start(services: services =>
    {
        PortfolioTestData.Register(services);
        services.AddSingleton(gold);
        services.AddSingleton<IPayrollSource>(new PortfolioPayroll(_ => throw new SourceUnavailable()));
    });

    private static IGoldReadPort Probe(Func<string, object?[]?, object?> read)
    {
        var port = DispatchProxy.Create<IGoldReadPort, StoredGoldProbe>();
        ((StoredGoldProbe)port).Read = read;
        return port;
    }

    private static Dictionary<string, object?> Map(params (string Key, object? Value)[] values) =>
        values.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);

    private sealed class ProbeScope : IDisposable
    {
        public void Dispose() { }
    }
}

public class StoredGoldProbe : DispatchProxy
{
    public Func<string, object?[]?, object?> Read { get; set; } = (_, _) => throw new InvalidOperationException();
    protected override object? Invoke(MethodInfo? targetMethod, object?[]? args) => Read(targetMethod!.Name, args);
}
