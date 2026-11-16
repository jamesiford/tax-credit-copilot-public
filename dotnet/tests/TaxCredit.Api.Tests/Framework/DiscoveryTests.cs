using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Endpoints;
using TaxCredit.Api.Hosting;

namespace TaxCredit.Api.Tests.Framework;

public sealed record DiscoveryValue(string Value, string Path);

public sealed class DiscoveryFeature : IFeatureModule
{
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration) =>
        services.AddSingleton(new DiscoveryValue(configuration["DISCOVERY_VALUE"] ?? "discovered",
            configuration["DISCOVERY_PATH"] ?? "/api/scope"));
}

public sealed class DiscoveryEndpoints : IEndpointGroup
{
    public void Map(IEndpointRouteBuilder endpoints) =>
        endpoints.MapGet(endpoints.ServiceProvider.GetRequiredService<DiscoveryValue>().Path,
            (DiscoveryValue value) => new { value = value.Value });
}

public sealed class DiscoveryTests
{
    [Fact]
    public async Task Production_discovery_registers_services_before_build_and_replaces_exactly_one_stub()
    {
        var (replaced, remaining) = await DeferredOperations.Pair();
        await using var host = await TestHost.Start(configuration: new Dictionary<string, string?>
        {
            ["TCC_FEATURE_ASSEMBLIES"] = typeof(DiscoveryFeature).Assembly.FullName,
            ["DISCOVERY_VALUE"] = "module-service",
            ["DISCOVERY_PATH"] = replaced.Path,
        });
        using var response = await host.Client.GetAsync(replaced.Path);
        Assert.Equal("""{"value":"module-service"}""", await response.Content.ReadAsStringAsync());
        DeferredOperations.AssertSingle(host.App, replaced);
        Assert.Single(host.App.Services.GetServices<DiscoveryValue>());
        DeferredOperations.AssertSingle(host.App, remaining);
        using var stub = await host.Client.GetAsync(remaining.Path);
        Assert.Equal(501, (int)stub.StatusCode);
    }
}
