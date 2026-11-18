using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Api.Contract;
using TaxCredit.Api.Endpoints;
using TaxCredit.Api.Wire;
using TaxCredit.Application;
using TaxCredit.Application.Features.Framework;
using TaxCredit.Application.Ports;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Infrastructure;
using TaxCredit.ServiceDefaults;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Hosting;

/// <summary>The only layer that names adapters; endpoint groups depend on application ports.</summary>
public static class HostComposition
{
    /// <summary>Registers real shared adapters, then discovered feature services, before provider construction.</summary>
    public static void AddSkeletonHost(this WebApplicationBuilder builder)
    {
        ArgumentNullException.ThrowIfNull(builder);
        builder.AddServiceDefaults();
        builder.Logging.AddFilter("Microsoft.AspNetCore.Hosting.Diagnostics", LogLevel.Warning);
        builder.Services.AddApplication().AddInfrastructure();
        builder.Services.AddTaxCreditRuntime(builder.Configuration);
        builder.Services.AddSingleton<RouteTable>();
        builder.Services.AddSingleton<RequestValidator>();
        builder.Services.AddScoped<IApiAccess, RuntimeAccess>();
        builder.Services.AddSingleton<ContractRequestGate>();
        if (builder.Configuration.Setting("CONTRACT_HOOKS") == "1")
        {
            builder.Services.AddSingleton<ContractTokenMinter>();
            builder.Services.TryAddSingleton<ITokenMinter>(s => s.GetRequiredService<ContractTokenMinter>());
            builder.Services.TryAddSingleton<IContractSigningKey>(s => s.GetRequiredService<ContractTokenMinter>());
        }

        builder.Services.ConfigureHttpJsonOptions(o => WireJson.Configure(o.SerializerOptions));
        builder.Services.AddCors(options => options.AddDefaultPolicy(policy => policy
            .WithOrigins((builder.Configuration["CORS_ORIGINS"] ?? "http://localhost:5173").Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
            .WithMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .WithHeaders("Content-Type", "Authorization", "X-TCC-Acting-User")));
        var features = new FeatureDiscovery(builder.Configuration);
        builder.Services.AddSingleton(features);
        features.ConfigureServices(builder.Services, builder.Configuration);
    }

    /// <summary>Installs standard CORS and routing, portable errors, and the discovered endpoint groups.</summary>
    public static void MapSkeletonHost(this WebApplication app)
    {
        app.UseSkeletonHost();
        app.MapEndpointGroups();
    }

    /// <summary>Shares startup, controls gate and wire middleware without imposing an executable's route surface.</summary>
    public static void UseSkeletonHost(this WebApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);
        app.Services.GetRequiredService<RuntimeStatus>().Settle();
        if (app.Configuration.Setting("CONTRACT_HOOKS") == "1")
        {
            // Force key creation at startup, not on the first request.
            _ = app.Services.GetRequiredService<ContractTokenMinter>();
            var gate = app.Services.GetRequiredService<ContractRequestGate>();
            app.Use(gate.Invoke);
        }

        app.UseRouting();
        app.UseCors();
        app.UseMiddleware<HostMiddleware>();
    }
}
