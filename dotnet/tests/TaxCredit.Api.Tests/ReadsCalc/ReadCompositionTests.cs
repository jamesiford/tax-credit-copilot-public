using System.Net;
using System.Text.Json;
using TaxCredit.Api.Tests.Contract;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class ReadCompositionTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Accepted_results_do_not_require_a_configured_payroll_source_and_fiscal_assumptions_are_explicit()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        await RuntimeRequests.Env(host, new { DATA_SOURCE = "lakehouse", FISCAL_RULES_POLICY = "assume" });
        var units = await StoredReadTests.Get(host, "/api/v2/clients/1001/units?year=2025");
        Assert.Equal("calculated", units.GetProperty("calculation_state").GetString());
        var eligibility = await StoredReadTests.Get(host, "/api/eligibility/2025?state=GA&account_id=1001");
        Assert.Equal(107, eligibility.GetProperty("employees_evaluated").GetInt32());
        Assert.True(eligibility.GetProperty("fiscal").GetProperty("assumed").GetBoolean());
        using var source = await host.Client.GetAsync("/api/forecast/2025?state=GA&account_id=1001");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, source.StatusCode);
        await RuntimeRequests.Env(host, new { FISCAL_RULES_POLICY = "strict" });
        using var strict = await host.Client.GetAsync("/api/eligibility/2025?state=GA&account_id=1001");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, strict.StatusCode);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public async Task One_host_reselects_source_and_fiscal_rules_after_each_profile_reset()
    {
        await using var host = await TestHost.Start();
        host.Client.Timeout = TimeSpan.FromMinutes(10);
        await RuntimeRequests.Reset(host);
        var first = await StoredReadTests.Get(host, "/api/scope");
        Assert.Equal("csv", first.GetProperty("data_source").GetString());
        await RuntimeRequests.Reset(host, "P2");
        var second = await StoredReadTests.Get(host, "/api/scope");
        Assert.Equal("lakehouse", second.GetProperty("data_source").GetString());
        Assert.Equal(4, second.GetProperty("clients").GetArrayLength());
        var matrix = await StoredReadTests.Get(host, "/api/onezero/matrix/2025?account_id=2002");
        Assert.Equal("2025-04-01", matrix.GetProperty("fiscal").GetProperty("begin").GetString());
        await RuntimeRequests.Reset(host);
        var third = await StoredReadTests.Get(host, "/api/scope");
        Assert.Equal("csv", third.GetProperty("data_source").GetString());
        Assert.Single(third.GetProperty("clients").EnumerateArray());
    }

    [Fact]
    public async Task Reconfiguring_auth_after_a_local_read_does_not_reuse_local_client_rights()
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        using var local = await host.Client.GetAsync("/api/v2/clients/1001/units");
        Assert.Equal(HttpStatusCode.OK, local.StatusCode);
        await RuntimeRequests.Env(host, new
        {
            AUTH_MODE = "entra",
            AUTH_TENANT_ID = "00000000-0000-0000-0000-0000000000aa",
            API_AUDIENCE = "api://11111111-2222-3333-4444-555555555555",
        });
        var restricted = await RuntimeRequests.Mint(host, new { kind = "user", oid = "00000000-0000-0000-0000-0000000000a3" });
        using var response = await RuntimeRequests.Send(host, restricted);
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(body.RootElement.TryGetProperty("detail", out _));
    }
}
