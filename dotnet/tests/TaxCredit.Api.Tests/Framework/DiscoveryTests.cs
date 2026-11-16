using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Endpoints;
using TaxCredit.Api.Hosting;

namespace TaxCredit.Api.Tests.Framework;

public sealed record DiscoveryValue(string Value);

public sealed class DiscoveryFeature : IFeatureModule
{
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration) =>
        services.AddSingleton(new DiscoveryValue(configuration["DISCOVERY_VALUE"] ?? "discovered"));
}

public sealed class DiscoveryEndpoints : IEndpointGroup
{
    public void Map(IEndpointRouteBuilder endpoints) =>
        endpoints.MapGet("/api/scope", (DiscoveryValue value) => new { value = value.Value });
}

public sealed class DiscoveryTests
{
    [Fact]
    public async Task Production_discovery_registers_services_before_build_and_replaces_exactly_one_stub()
    {
        await using var host = await TestHost.Start(configuration: new Dictionary<string, string?>
        {
            ["TCC_FEATURE_ASSEMBLIES"] = typeof(DiscoveryFeature).Assembly.FullName,
            ["DISCOVERY_VALUE"] = "module-service",
        });
        using var response = await host.Client.GetAsync("/api/scope");
        Assert.Equal("""{"value":"module-service"}""", await response.Content.ReadAsStringAsync());
        var endpoints = ((IEndpointRouteBuilder)host.App).DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>();
        Assert.Single(endpoints, e => e.RoutePattern.RawText == "/api/scope");
        Assert.Single(host.App.Services.GetServices<DiscoveryValue>());
        using var stub = await host.Client.GetAsync("/api/rules");
        Assert.Equal(501, (int)stub.StatusCode);
    }
}
