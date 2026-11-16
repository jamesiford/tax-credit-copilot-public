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

namespace TaxCredit.Api.Hosting;

/// <summary>The only layer that names adapters; endpoint groups depend on application ports.</summary>
public static class HostComposition
{
    /// <summary>Registers the framework and hermetic seams, with replaceable no-op persistence.</summary>
    public static void AddSkeletonHost(this WebApplicationBuilder builder)
    {
        ArgumentNullException.ThrowIfNull(builder);
        builder.AddServiceDefaults();
        builder.Logging.AddFilter("Microsoft.AspNetCore.Hosting.Diagnostics", LogLevel.Warning);
        builder.Services.AddApplication().AddInfrastructure();
        builder.Services.AddSingleton<RouteTable>();
        builder.Services.AddSingleton<RequestValidator>();
        builder.Services.AddSingleton<RuntimeConfiguration>();
        builder.Services.TryAddSingleton<IRuntimeConfiguration>(s => s.GetRequiredService<RuntimeConfiguration>());
        builder.Services.AddSingleton(_ => new RuntimeSources(builder.Configuration["TCC_CONTRACT_HOOKS"] == "1"));
        builder.Services.TryAddSingleton<IClock>(s => s.GetRequiredService<RuntimeSources>());
        builder.Services.TryAddSingleton<IIdSource>(s => s.GetRequiredService<RuntimeSources>());
        builder.Services.TryAddSingleton<ISecretSource>(s => s.GetRequiredService<RuntimeSources>());
        builder.Services.TryAddSingleton<IContractWork, NoContractWork>();
        builder.Services.TryAddSingleton<IApiAccess, SkeletonAccess>();
        builder.Services.TryAddSingleton<IHostStatus, SkeletonHostStatus>();
        builder.Services.AddSingleton<ContractRequestGate>();
        if (builder.Configuration["TCC_CONTRACT_HOOKS"] == "1")
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
    }

    /// <summary>Installs standard CORS and routing, portable errors, and the discovered endpoint groups.</summary>
    public static void MapSkeletonHost(this WebApplication app)
    {
        ArgumentNullException.ThrowIfNull(app);
        if (app.Configuration["TCC_CONTRACT_HOOKS"] == "1")
        {
            // Force key creation at startup, not on the first request.
            _ = app.Services.GetRequiredService<ContractTokenMinter>();
            var gate = app.Services.GetRequiredService<ContractRequestGate>();
            app.Use(gate.Invoke);
        }

        app.UseRouting();
        app.UseCors();
        app.UseMiddleware<HostMiddleware>();
        app.MapEndpointGroups();
    }
}
