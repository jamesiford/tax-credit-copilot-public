using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.DataMap;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>The outward composition root is shared by the API and Worker, without either host referencing the other.</summary>
public static class RuntimeRegistration
{
    /// <summary>Registers one durable destination and real adapters before feature registration and provider construction.</summary>
    public static IServiceCollection AddTaxCreditRuntime(this IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(configuration);
        var settings = new RuntimeConfiguration(configuration);
        LegacySettingAliases.Report(configuration, Console.Error.WriteLine);
        var dataMap = DataMapLoader.Load(settings.Get("DATA_MAP_FILE"));
        var names = new PhysicalNames(dataMap);
        PhysicalNames.Use(names);
        services.AddSingleton(dataMap);
        services.AddSingleton(names);
        var paths = new RuntimePaths(settings);
        var hooks = configuration.Setting("CONTRACT_HOOKS") == "1";
        Validate(settings, hooks);
        services.AddSingleton(settings);
        services.AddSingleton<IRuntimeConfiguration>(settings);
        services.AddSingleton(paths);
        services.AddSingleton(new RuntimeSources(hooks));
        services.AddSingleton<IClock>(s => s.GetRequiredService<RuntimeSources>());
        services.AddSingleton<IIdSource>(s => s.GetRequiredService<RuntimeSources>());
        services.AddSingleton<ISecretSource>(s => s.GetRequiredService<RuntimeSources>());
        services.AddSingleton<TimeProvider>(s => s.GetRequiredService<RuntimeSources>());
        services.TryAddSingleton(new DefaultAzureCredential());
        var provider = settings.Get("PERSISTENCE_PROVIDER");
        PersistenceDatabase database;
        if (provider == "sqlite")
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(paths.Database))!);
            database = PersistenceDatabase.Sqlite(paths.Database, names: names);
        }
        else if (provider is "sqlserver" or "warehouse")
        {
            var connections = new EntraSqlConnections(Required(settings, "FABRIC_SQL_SERVER"),
                settings.Get("FABRIC_SQL_DATABASE") is { Length: > 0 } warehouse ? warehouse
                    : dataMap.WarehouseDatabase ?? Required(settings, "FABRIC_SQL_DATABASE"), new CredentialSqlTokens(new DefaultAzureCredential()));
            database = connections.Database(bulk: BulkLoadPolicy.FromSettings(settings.Get), names: names);
            services.AddSingleton(connections);
        }
        else
        {
            throw new InvalidOperationException("Unknown PERSISTENCE_PROVIDER.");
        }

        services.AddPersistence(database, paths.Repository, paths.Seeds, retention: GoldRetention.FromSettings(settings.Get));
        services.AddRuntimeSources(settings, paths, dataMap);
        services.AddRuntimeCalculation(settings, paths);
        services.AddRuntimeTrust(settings);
        services.AddRuntimeAi(settings);
        services.AddRuntimeArtifacts(settings, paths, hooks);
        services.AddSingleton<RunWorkGate>();
        services.AddSingleton(ExecutionOptions(settings));
        services.AddSingleton<RunWorkExecutor>();
        services.AddSingleton<IContractWork, RuntimeContractWork>();
        services.AddSingleton<RuntimeStatus>();
        services.AddSingleton<TaxCredit.Application.Features.Framework.IHostStatus>(p => p.GetRequiredService<RuntimeStatus>());
        return services;
    }

    // RUN_LEASE_SECONDS (default 600) is how long a silent worker keeps an item; RUN_LEASE_RENEW_SECONDS (default a third of it) is how often a running item renews.
    private static RunExecutionOptions ExecutionOptions(RuntimeConfiguration settings)
    {
        int Whole(string key, int fallback)
        {
            var text = settings.Get(key);
            return string.IsNullOrWhiteSpace(text) ? fallback
                : int.TryParse(text, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out var value) && value >= 1 ? value
                : throw new InvalidOperationException("Invalid setting " + key + ": a whole number of seconds, at least 1.");
        }

        var lease = Whole("RUN_LEASE_SECONDS", 600);
        var renew = Whole("RUN_LEASE_RENEW_SECONDS", 0);
        return renew >= lease && settings.Get("RUN_LEASE_RENEW_SECONDS") is not null
            ? throw new InvalidOperationException("RUN_LEASE_RENEW_SECONDS must be shorter than RUN_LEASE_SECONDS.")
            : new RunExecutionOptions(lease, RenewSeconds: renew);
    }

    internal static string Required(IRuntimeConfiguration settings, string key) =>
        string.IsNullOrWhiteSpace(settings.Get(key)) ? throw new InvalidOperationException("Required setting: " + key) : settings.Get(key)!;

    internal static bool Flag(IRuntimeConfiguration settings, string key) => settings.Get(key)?.Trim().ToLowerInvariant() switch
    {
        "true" or "1" or "yes" => true,
        null or "" or "false" or "0" or "no" => false,
        _ => throw new InvalidOperationException("Invalid boolean setting: " + key),
    };

    private static void Validate(RuntimeConfiguration settings, bool hooks)
    {
        if (settings.Get("ENVIRONMENT") != "local"
            && (hooks || settings.Get("PERSISTENCE_PROVIDER") != "warehouse" || settings.Get("DATA_SOURCE") != "lakehouse"
                || settings.Get("ARTIFACT_STORE") != "blob"))
        {
            throw new InvalidOperationException("Deployed hosts require Warehouse, lakehouse SQL and Blob; replay controls are local-only.");
        }
    }
}
