using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Calculations;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Calculations;

public sealed class CalculationBoundaryTests
{
    [Fact]
    public async Task Legacy_performance_uses_source_year_tag_but_onezero_buckets_by_pay_date()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IClientPayrollSource>(new SmallPayroll()));
        using var scope = host.App.Services.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
        var args = Args(("tax_year", "2025"), ("state", "GA"), ("account_id", "1001"));
        var performance = JsonSerializer.SerializeToElement(service.Execute("performance", args));
        Assert.Equal(0, performance.GetProperty("totals").GetProperty("total").GetInt32());
        var onezero = JsonSerializer.SerializeToElement(service.Execute("onezero", args));
        Assert.Equal(12, onezero.GetProperty("row_count").GetInt32());
        Assert.Single(onezero.GetProperty("results").EnumerateArray());
    }

    [Fact]
    public async Task Reviews_survive_scope_reopening_use_attributed_reviewer_and_clear_durably()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IClientPayrollSource>(new SmallPayroll()));
        using (var first = host.App.Services.CreateScope())
        {
            var service = first.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
            using var body = JsonDocument.Parse("""{"status":"flagged","note":"check","actor":"spoofed"}""");
            service.Execute("review_employee", Args(("employee_id", "synthetic-employee"), ("reviewer", "actual-reviewer")), body.RootElement);
        }
        using (var next = host.App.Services.CreateScope())
        {
            var service = next.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
            var detail = JsonSerializer.SerializeToElement(service.Execute("onezero_employee",
                Args(("employee_id", "synthetic-employee"), ("tax_year", "2025"), ("state", "GA"))));
            Assert.Equal("actual-reviewer", detail.GetProperty("review").GetProperty("reviewer").GetString());
            service.Execute("review_employee", Args(("employee_id", "synthetic-employee"), ("status", "cleared")));
        }
        using var final = host.App.Services.CreateScope();
        var cleared = JsonSerializer.SerializeToElement(final.ServiceProvider.GetRequiredService<ReadsCalculationViews>()
            .Execute("onezero_employee", Args(("employee_id", "synthetic-employee"), ("tax_year", "2025"), ("state", "GA"))));
        Assert.Equal(JsonValueKind.Null, cleared.GetProperty("review").ValueKind);
    }

    [Fact]
    public async Task Unavailable_source_and_unknown_tenant_are_not_successful_empty_reports()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IClientPayrollSource>(new SmallPayroll()));
        using var scope = host.App.Services.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
        Assert.Equal(404, Assert.Throws<ReadRefusalException>(() => service.Execute("forecast", Args(("account_id", "9999")))).StatusCode);
        Assert.Throws<SourceUnavailable>(() => service.Execute("forecast", Args(("account_id", "8888"))));
        Assert.Equal(422, Assert.Throws<ReadRefusalException>(() => service.Execute("simulate_portfolio",
            Args(("state", "GA"), ("magnitude", "10001")))).StatusCode);
    }

    private static Dictionary<string, string?> Args(params (string Key, string? Value)[] fields) =>
        fields.ToDictionary(field => field.Key, field => field.Value, StringComparer.Ordinal);

    private sealed class SmallPayroll : IClientPayrollSource, ISourceReader
    {
        public long? FixtureAccountId => 1001;
        public bool IsConfigured => true;
        public IReadOnlyList<SourceAccount> ListAccounts() => [new(1001, "Synthetic boundary client", "GA")];
        public IReadOnlyDictionary<long, IReadOnlyList<string>> Footprint() =>
            new Dictionary<long, IReadOnlyList<string>> { [1001] = ["GA"] };
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
        {
            if (accountId == 8888)
            {
                throw new SourceUnavailable();
            }
            if (accountId is not (null or 1001))
            {
                return [];
            }
            return Enumerable.Range(1, 12).Select(month => PayRow.Of(new PyDict()
                .Add("Employee_ID", "synthetic-employee").Add("Worksite_ID", "GA_TEST").Add("Entity_FEIN", "synthetic-entity")
                .Add("Pay_Period_Start", $"{2025}-{month:00}-01").Add("Pay_Period_End", $"{2025}-{month:00}-{DateTime.DaysInMonth(2025, month):00}")
                .Add("Pay_Date", $"{2025}-{month:00}-{DateTime.DaysInMonth(2025, month):00}").Add("Tax_Year", 2024L)
                .Add("Hours_Worked", 200.0).Add("Gross_Wages", 5000.0).Add("Pay_Code", "Regular"))).ToList();
        }
        public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> LoadPortfolioPayPeriods() => new Dictionary<long, IReadOnlyList<PayRow>> { [1001] = LoadPayPeriods(1001) };
        public FiscalWindow ClientFiscalWindow(long? accountId, long taxYear, string convention) =>
            new(new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31), taxYear, convention, "synthetic");
        public FiscalWindow? FiscalWindowForStateYear(long? accountId, string state, long taxYear) => ClientFiscalWindow(accountId, taxYear, "ends");
        public (DateOnly Begin, DateOnly End)? WindowForStateYear(long? accountId, string state, long taxYear) =>
            (new DateOnly((int)taxYear, 1, 1), new DateOnly((int)taxYear, 12, 31));
    }
}
