using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using TaxCredit.Api.Hosting;

namespace TaxCredit.Api.Tests;

internal sealed class TestHost(WebApplication app, HttpClient client, string ownedRoot) : IAsyncDisposable
{
    internal WebApplication App { get; } = app;
    internal HttpClient Client { get; } = client;

    internal static async Task<TestHost> Start(bool hooks = true, Action<WebApplication>? routes = null, Action<IServiceCollection>? services = null,
        IReadOnlyDictionary<string, string?>? configuration = null)
    {
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Production" });
        var ownedRoot = Directory.CreateDirectory(Path.Combine(Corpus.Root, "dotnet", "artifacts", "host-tests", Guid.NewGuid().ToString("N"))).FullName;
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["TCC_CONTRACT_HOOKS"] = hooks ? "1" : "0",
            ["AUTH_MODE"] = "none",
            ["ENVIRONMENT"] = "local",
            ["DATA_SOURCE"] = "csv",
            ["FOUNDRY_PROJECT_ENDPOINT"] = "",
            ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "",
            ["CORS_ORIGINS"] = "http://localhost:5173",
            ["OPERATIONAL_DB"] = Path.Combine(ownedRoot, "operations.db"),
            ["ARTIFACT_LOCAL_ROOT"] = Path.Combine(ownedRoot, "bytes"),
        });
        if (configuration is not null)
        {
            builder.Configuration.AddInMemoryCollection(configuration);
        }

        builder.WebHost.UseTestServer();
        builder.AddSkeletonHost();
        services?.Invoke(builder.Services);
        var app = builder.Build();
        app.Use((context, next) =>
        {
            context.Connection.RemoteIpAddress = IPAddress.Loopback;
            return next(context);
        });
        routes?.Invoke(app);
        app.MapSkeletonHost();
        await app.StartAsync();
        return new TestHost(app, app.GetTestClient(), ownedRoot);
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.DisposeAsync();
        Directory.Delete(ownedRoot, recursive: true);
    }
}
