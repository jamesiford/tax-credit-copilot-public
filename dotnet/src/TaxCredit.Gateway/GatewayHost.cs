using TaxCredit.Api.Endpoints.Contract;
using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.Framework;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Execution;
using TaxCredit.Gateway.Mcp;
using TaxCredit.Gateway.Trust;
using TaxCredit.Infrastructure.Auth;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Gateway;

/// <summary>Ordinary in-process channel composition; no API process or loopback transport is required.</summary>
public static class GatewayHost
{
    /// <summary>Tests may select a transport before build, using the same application and adapter graph.</summary>
    public static WebApplication Build(string[] args, Action<WebApplicationBuilder>? configure = null,
        Action<IServiceCollection>? configureServices = null)
    {
        var builder = WebApplication.CreateBuilder(args);
        configure?.Invoke(builder);
        builder.Configuration["AUTH_MODE"] = "entra";
        builder.AddSkeletonHost();
        builder.Services.AddScoped<ChannelAuthenticator>();
        builder.Services.AddSingleton<ChannelCatalog>();
        builder.Services.AddSingleton<ChannelState>();
        builder.Services.AddSingleton<McpSessions>();
        builder.Services.AddScoped<ChannelAudit>();
        builder.Services.AddScoped<ToolPipeline>();
        builder.Services.AddScoped<ChannelDownloads>();
        builder.Services.AddScoped<NarrationAudit>();
        // The channel is not the portal's optional local-writer mode: even a preview needs entitlement.
        builder.Services.AddScoped<IWriterPolicy>(provider => new WriterPolicy(provider.GetRequiredService<IWriterEntitlement>(), true));
        builder.Services.AddSingleton<RuntimeContractWork>();
        builder.Services.AddSingleton<IContractWork, GatewayContractWork>();
        configureServices?.Invoke(builder.Services);
        var app = builder.Build();
        ChannelConfiguration.Validate(app.Services.GetRequiredService<RuntimeConfiguration>());
        app.UseSkeletonHost();
        app.UseMiddleware<ChannelBoundary>();
        app.MapGet("/api/health", async (IMediator mediator, CancellationToken ct) =>
            Results.Json(await mediator.Send(new GetHealthQuery(), ct).ConfigureAwait(false)));
        new ContractEndpoints(app.Configuration).Map(app);
        ChannelEndpoints.Map(app);
        return app;
    }
}

internal sealed class GatewayContractWork(RuntimeContractWork inner, RuntimeConfiguration settings, ChannelState state, McpSessions sessions) : IContractWork
{
    public ValueTask<int> Drain(CancellationToken cancellationToken) => inner.Drain(cancellationToken);

    public async ValueTask Reset(string profile, CancellationToken cancellationToken)
    {
        await inner.Reset(profile, cancellationToken).ConfigureAwait(false);
        state.Reset(profile == "G1L" ? 6 : profile == "G1" ? 1000 : null);
        await sessions.ResetAsync().ConfigureAwait(false);
        await EnvironmentChanged(cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask EnvironmentChanged(CancellationToken cancellationToken)
    {
        // API scenario setup can request anonymous mode; the channel never has an anonymous mode.
        settings.Apply(new Dictionary<string, string>(StringComparer.Ordinal) { ["AUTH_MODE"] = "entra" }, []);
        ChannelConfiguration.Validate(settings);
        await inner.EnvironmentChanged(cancellationToken).ConfigureAwait(false);
        state.ClearRateLimits();
    }
}
