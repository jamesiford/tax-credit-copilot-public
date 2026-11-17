using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class SourceLimitResponseTests
{
    [Fact]
    public async Task An_oversize_client_is_a_422_whose_remedy_names_the_setting_and_the_limit()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IClientPayrollSource>(new RefusingSource()));
        using var response = await host.Client.GetAsync("/api/forecast/2025?state=GA&account_id=1001");
        Assert.Equal(422, (int)response.StatusCode);
        var body = (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail");
        Assert.Equal("account_too_large", body.GetProperty("code").GetString());
        var remedy = body.GetProperty("remedy").GetString()!;
        Assert.Contains("SOURCE_MAX_ACCOUNT_ROWS", remedy, StringComparison.Ordinal);
        Assert.Contains("1,000,000", remedy, StringComparison.Ordinal);
    }

    [Fact]
    public async Task A_portfolio_over_its_bounds_is_a_422_that_says_to_select_fewer_clients()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IClientPayrollSource>(new RefusingSource()));
        using var response = await host.Client.GetAsync("/api/simulate/portfolio/2025?state=GA");
        Assert.Equal(422, (int)response.StatusCode);
        var body = (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("detail");
        Assert.Equal("portfolio_too_large", body.GetProperty("code").GetString());
        var remedy = body.GetProperty("remedy").GetString()!;
        Assert.Contains("SOURCE_PORTFOLIO_MAX_ACCOUNTS", remedy, StringComparison.Ordinal);
        Assert.Contains("Select fewer clients", remedy, StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_host_reads_the_limits_from_settings_and_keeps_the_defaults_otherwise()
    {
        await using (var plain = await TestHost.Start())
        {
            Assert.Equal(SourceLimits.Default, plain.App.Services.GetRequiredService<SourceLimits>());
        }
        var set = new Dictionary<string, string?> { ["SOURCE_MAX_ACCOUNT_ROWS"] = "2000000", ["SOURCE_PORTFOLIO_MAX_ACCOUNTS"] = "4", ["SOURCE_PORTFOLIO_MAX_ROWS"] = "9000" };
        await using var tuned = await TestHost.Start(configuration: set);
        Assert.Equal(new SourceLimits(2_000_000, 4, 9000), tuned.App.Services.GetRequiredService<SourceLimits>());
    }

    [Fact]
    public async Task An_invalid_limit_stops_the_host_at_startup()
    {
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            TestHost.Start(configuration: new Dictionary<string, string?> { ["SOURCE_MAX_ACCOUNT_ROWS"] = "500" }));
        Assert.StartsWith("SOURCE_MAX_ACCOUNT_ROWS must be", error.Message, StringComparison.Ordinal);
    }

    private sealed class RefusingSource : IClientPayrollSource, ISourceReader
    {
        public long? FixtureAccountId => 1001;
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() => [new(1001, "Synthetic client", "GA")];
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => new Dictionary<long, IReadOnlyList<string>> { [1001] = ["GA"] };
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => throw new SourceTooLarge(1_000_000);
        public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods() => throw SourcePortfolioTooLarge.ForAccounts(26, 25);
        public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) =>
            new(new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31), taxYear, convention, "synthetic");
        public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) => ClientFiscalWindow(accountId, taxYear, "ends");
        public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
            (new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31));
    }
}
