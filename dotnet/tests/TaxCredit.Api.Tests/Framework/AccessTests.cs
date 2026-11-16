using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports;

namespace TaxCredit.Api.Tests.Framework;

public sealed class AccessTests
{
    private sealed class Refuse : IApiAccess
    {
        public ValueTask<ApiAccessDecision> Check(ApiAccessRequest request, CancellationToken cancellationToken) =>
            ValueTask.FromResult(new ApiAccessDecision(false, 403, "writer required"));
    }

    [Fact]
    public async Task The_real_authentication_adapter_refuses_missing_and_invalid_tokens()
    {
        await using var host = await TestHost.Start(hooks: false, configuration: new Dictionary<string, string?>
        {
            ["AUTH_MODE"] = "entra",
            ["AUTH_TENANT_ID"] = "00000000-0000-0000-0000-0000000000aa",
            ["API_AUDIENCE"] = "api://11111111-2222-3333-4444-555555555555",
        });
        using var noToken = await host.Client.GetAsync("/api/scope");
        Assert.Equal(401, (int)noToken.StatusCode);
        Assert.Equal("Bearer", Assert.Single(noToken.Headers.WwwAuthenticate).Scheme);
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/scope");
        request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", "not-a-validated-token");
        using var unsigned = await host.Client.SendAsync(request);
        Assert.Equal(401, (int)unsigned.StatusCode);
        using var publicProbe = await host.Client.GetAsync("/api/health");
        Assert.Equal(200, (int)publicProbe.StatusCode);
    }

    [Fact]
    public async Task Auth_adapter_refusals_are_applied_to_stubs_before_dispatch()
    {
        await using var host = await TestHost.Start(services: services => services.AddSingleton<IApiAccess, Refuse>());
        using var response = await host.Client.PostAsync("/api/claims", new StringContent("{}"));
        Assert.Equal(403, (int)response.StatusCode);
        Assert.Equal("""{"detail":"writer required"}""", await response.Content.ReadAsStringAsync());
    }
}
