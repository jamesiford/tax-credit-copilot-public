using System.Globalization;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using Xunit;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class AssessmentTests
{
    [Fact]
    public async Task Assessment_sweeps_all_years_but_targeted_refresh_preserves_the_filing_and_prior_year_base()
    {
        await using var host = await TestHost.Start(services: services =>
            services.Replace(ServiceDescriptor.Singleton<IClientPayrollSource>(new SmallPayroll())));
        (await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" })).EnsureSuccessStatusCode();
        var all = await Json(await host.Client.PostAsJsonAsync("/api/claims/assess", new { client_id = 5555, program_code = "GA_JTC" }));
        Assert.Equal(new[] { 2023, 2024, 2025 }, all.GetProperty("years").EnumerateArray().Select(y => y.GetInt32()));
        var cells = all.GetProperty("assessed");
        Assert.Equal(3, cells.GetArrayLength());
        Assert.Equal(cells[0].GetProperty("average_headcount").GetDouble(), cells[0].GetProperty("base_average_headcount").GetDouble());
        Assert.True(cells[0].GetProperty("is_base_year").GetBoolean());
        (await host.Client.PostAsJsonAsync("/api/claims/cell/5555/GA_JTC/2025/transition",
            new { status = "proposed" })).EnsureSuccessStatusCode();
        var targeted = await Json(await host.Client.PostAsJsonAsync("/api/claims/assess",
            new { client_id = 5555, program_code = "GA_JTC", tax_years = new[] { 2025 } }));
        var refreshed = Assert.Single(targeted.GetProperty("assessed").EnumerateArray());
        Assert.Equal("proposed", refreshed.GetProperty("status").GetString());
        Assert.Equal(cells[2].GetProperty("base_average_headcount").GetDouble(), refreshed.GetProperty("base_average_headcount").GetDouble());
        Assert.True(refreshed.GetProperty("base_average_headcount").GetDouble() > 0);
        Assert.True(refreshed.GetProperty("average_headcount").GetDouble() > refreshed.GetProperty("base_average_headcount").GetDouble());
        using var scope = host.App.Services.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IClaimRepository>();
        Assert.Single(repository.History(5555, "GA_JTC", 2024));
        Assert.Equal(3, repository.History(5555, "GA_JTC", 2025).Count);
        Assert.Empty(repository.History(5555, "SC_JTC", 2025));
    }

    private static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }

    private sealed class SmallPayroll : IClientPayrollSource, ISourceReader
    {
        private readonly IReadOnlyList<PayRow> _rows = Build();
        public long? FixtureAccountId => 5555;
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() => [new(5555, "Synthetic assessment fixture")];
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() => new Dictionary<long, IReadOnlyList<string>> { [5555] = ["GA"] };
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => accountId == 5555 ? _rows : [];
        public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods() => new Dictionary<long, IReadOnlyList<PayRow>> { [5555] = _rows };
        public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) => FiscalWindow.AssumedCalendar(taxYear, convention);
        public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) => ClientFiscalWindow(accountId, taxYear, "begins");
        public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
            (new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31));

        private static List<PayRow> Build()
        {
            var rows = new List<PayRow>();
            foreach (var year in new[] { 2023, 2024, 2025 })
            {
                for (var week = 0; week < 51; week++)
                {
                    var start = new DateOnly(year, 1, 1).AddDays(7 * week);
                    for (var person = 0; person < 2 * (year - 2022); person++)
                    {
                        rows.Add(PayRow.Of(new PyDict().Add("Employee_ID", $"SYNTHETIC-{person}")
                            .Add("Worksite_ID", "GA_SYNTHETIC").Add("Work_State", "GA")
                            .Add("Pay_Period_Start", start.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))
                            .Add("Pay_Period_End", start.AddDays(6).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))
                            .Add("Pay_Date", start.AddDays(11).ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))
                            .Add("Hours_Worked", 40L).Add("Gross_Wages", 1000L).Add("Pay_Code", "Regular")));
                    }
                }
            }
            return rows;
        }
    }
}
