using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using TaxCredit.Api.Tests.Contract;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class StoredReadTests
{
    [Fact]
    public async Task Population_totals_do_not_follow_filter_or_page_and_the_two_verdicts_remain_distinct()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var all = await Get(host, "/api/eligibility/2025?state=GA&account_id=1001&limit=1");
        var filtered = await Get(host, "/api/eligibility/2025?state=GA&account_id=1001&status=both&limit=2");
        Assert.Equal(107, all.GetProperty("employees_evaluated").GetInt32());
        Assert.Equal(77, all.GetProperty("min_max_eligible").GetInt32());
        Assert.Equal(72, all.GetProperty("pay_period_eligible").GetInt32());
        Assert.Equal(107, filtered.GetProperty("employees_evaluated").GetInt32());
        Assert.Equal(72, filtered.GetProperty("total").GetInt32());
        Assert.Equal(2, filtered.GetProperty("rows").GetArrayLength());
        Assert.Equal(1, all.GetProperty("rows").GetArrayLength());
    }

    [Fact]
    public async Task Unit_month_and_independent_filters_narrow_rows_not_the_population()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var baseline = await Get(host, "/api/v2/clients/1001/units/GA_ATL_HQ?year=2025&limit=2");
        var filtered = await Get(host, "/api/v2/clients/1001/units/GA_ATL_HQ?year=2025&limit=1&filter=avg_weekly_hours:>=999");
        Assert.True(baseline.GetProperty("total_unfiltered").GetInt32() > 2, baseline.ToString());
        Assert.Equal(baseline.GetProperty("near_total_unfiltered").GetInt32(), filtered.GetProperty("near_total_unfiltered").GetInt32());
        Assert.Equal(baseline.GetProperty("total_unfiltered").GetInt32(), filtered.GetProperty("total_unfiltered").GetInt32());
        using var invalid = await host.Client.GetAsync("/api/v2/clients/1001/units/GA_ATL_HQ?year=2025&month=13");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, invalid.StatusCode);
        Assert.True((await invalid.Content.ReadFromJsonAsync<JsonElement>()).TryGetProperty("detail", out _));
    }

    [Fact]
    public async Task Reopening_the_same_operational_store_retains_accepted_run_identity_and_values()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        var original = await Get(host, "/api/onezero/matrix/2025?account_id=1001");
        await using var reopened = await TestHost.Start(configuration: new Dictionary<string, string?>(StringComparer.Ordinal)
        {
            ["OPERATIONAL_DB"] = host.App.Configuration["OPERATIONAL_DB"],
        });
        var persisted = await Get(reopened, "/api/onezero/matrix/2025?account_id=1001");
        Assert.Equal(original.GetProperty("run").GetProperty("run_id").GetString(), persisted.GetProperty("run").GetProperty("run_id").GetString());
        Assert.Equal(original.GetProperty("annual_average").GetDouble(), persisted.GetProperty("annual_average").GetDouble());
        Assert.Equal(original.GetProperty("matrix").GetArrayLength(), persisted.GetProperty("matrix").GetArrayLength());
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task Opaque_handles_are_client_bound_and_uncalculated_years_are_not_zero_results()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host, "P2");
        var unit = await Get(host, "/api/v2/clients/2001/units/GA_GA-001?year=2023&limit=1");
        var token = unit.GetProperty("employees")[0].GetProperty("record_token").GetString();
        using var wrong = await host.Client.GetAsync($"/api/v2/employees/{token}?client_id=2002&year=2023");
        Assert.Equal(HttpStatusCode.NotFound, wrong.StatusCode);
        var absent = await Get(host, "/api/v2/clients/2001/units/GA_GA-001?year=2019");
        Assert.Equal("not_calculated", absent.GetProperty("calculation_state").GetString());
        Assert.Null(absent.GetProperty("unit").Deserialize<object>());
        using var huge = await host.Client.GetAsync("/api/v2/clients/9223372036854775808/units");
        Assert.Equal(HttpStatusCode.UnprocessableEntity, huge.StatusCode);
    }

    internal static async Task<JsonElement> Get(TestHost host, string path)
    {
        using var response = await host.Client.GetAsync(path);
        var json = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.True(response.IsSuccessStatusCode, $"{path}: {(int)response.StatusCode}: {json}");
        return json;
    }
}
