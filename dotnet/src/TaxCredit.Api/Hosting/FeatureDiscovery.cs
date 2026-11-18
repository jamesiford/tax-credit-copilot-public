using System.Reflection;
using System.Runtime.Loader;
using TaxCredit.Api.Endpoints;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Hosting;

/// <summary>Feature-owned registrations execute before the provider is built.</summary>
public interface IFeatureModule
{
    /// <summary>Registers inward handlers and collaborators, never a temporary provider.</summary>
    void ConfigureServices(IServiceCollection services, IConfiguration configuration);
}

/// <summary>One deterministic assembly inventory drives both pre-build services and post-build routes.</summary>
public sealed class FeatureDiscovery
{
    /// <summary>Additional assemblies are an explicit trusted deployment setting, not request input.</summary>
    public FeatureDiscovery(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        var assemblies = new[] { typeof(IEndpointGroup).Assembly, typeof(Application.DependencyInjection).Assembly }
            .Concat((configuration.Setting("FEATURE_ASSEMBLIES") ?? "").Split(';', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
                .Select(name => Path.IsPathFullyQualified(name)
                    ? AssemblyLoadContext.Default.LoadFromAssemblyPath(name) : Assembly.Load(name)));
        Types = assemblies.Distinct().OrderBy(a => a.FullName, StringComparer.Ordinal)
            .SelectMany(a => a.GetTypes()).Where(t => t is { IsClass: true, IsAbstract: false, IsPublic: true })
            .OrderBy(t => t.FullName, StringComparer.Ordinal).ToArray();
    }

    /// <summary>The same discovered types are reused during endpoint mapping.</summary>
    public IReadOnlyList<Type> Types { get; }

    /// <summary>Modules are parameterless declarations; DI resolution happens after all registrations.</summary>
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        foreach (var type in Types.Where(t => typeof(IFeatureModule).IsAssignableFrom(t)))
        {
            ((IFeatureModule)Activator.CreateInstance(type)!).ConfigureServices(services, configuration);
        }
    }
}
