using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Api.Tests.Ai;

internal sealed class AiSocketHost(WebApplication app, HttpClient client, string ownedRoot,
    TaskCompletionSource scopeDisposed) : IAsyncDisposable
{
    internal HttpClient Client { get; } = client;
    internal IServiceProvider Services => app.Services;
    internal Task ScopeDisposed => scopeDisposed.Task;

    internal static async Task<AiSocketHost> Start(IAiNarrator? narrator = null, Action<IServiceCollection>? configure = null)
    {
        var root = Directory.CreateDirectory(Path.Combine(Corpus.Root, "dotnet", "artifacts", "ai-socket-tests", Guid.NewGuid().ToString("N"))).FullName;
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Production" });
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["TCC_CONTRACT_HOOKS"] = "0",
            ["AUTH_MODE"] = "none",
            ["ENVIRONMENT"] = "local",
            ["DATA_SOURCE"] = "csv",
            ["FOUNDRY_PROJECT_ENDPOINT"] = "",
            ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "",
            ["OPERATIONAL_DB"] = Path.Combine(root, "ops.db"),
            ["ARTIFACT_LOCAL_ROOT"] = Path.Combine(root, "bytes")
        });
        builder.WebHost.UseKestrel().UseUrls("http://127.0.0.1:0");
        builder.AddSkeletonHost();
        var disposed = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        builder.Services.AddScoped(_ => new ScopeSignal(disposed));
        builder.Services.AddScoped<IPageFactSource>(provider =>
        {
            _ = provider.GetRequiredService<ScopeSignal>();
            return new StreamFacts();
        });
        builder.Services.AddScoped<IPageScope, StreamFacts>();
        if (narrator is not null) { builder.Services.AddSingleton(narrator); }
        configure?.Invoke(builder.Services);
        var app = builder.Build();
        app.MapSkeletonHost();
        await app.StartAsync();
        var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
        return new(app, new HttpClient { BaseAddress = new Uri(address), Timeout = TimeSpan.FromSeconds(10) }, root, disposed);
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await app.DisposeAsync();
        Directory.Delete(ownedRoot, recursive: true);
    }

    private sealed class ScopeSignal(TaskCompletionSource disposed) : IDisposable
    {
        public void Dispose() => disposed.TrySetResult();
    }
}
