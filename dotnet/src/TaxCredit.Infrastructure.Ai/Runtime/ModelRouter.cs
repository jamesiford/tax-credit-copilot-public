using System.Collections.Concurrent;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Runtime;

/// <summary>Root-owned provider factories; duplicate labels fail rather than depend on registration order.</summary>
public sealed class ProviderRegistry
{
    private readonly Dictionary<string, Func<IAgentRuntime>> _factories = [with(StringComparer.Ordinal)];
    /// <summary>Registers without constructing or calling a provider.</summary>
    public void Register(string name, Func<IAgentRuntime> factory)
    {
        if (!_factories.TryAdd(name, factory))
        {
            throw new ModelException(ModelErrorKind.Configuration, "duplicate_provider");
        }
    }
    /// <summary>Builds exactly the requested registered adapter.</summary>
    public IAgentRuntime Build(string name)
    {
        if (!_factories.TryGetValue(name, out var factory))
        {
            throw new ModelException(ModelErrorKind.Configuration, "unknown_provider");
        }
        try { return factory(); }
        catch (ModelException) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Configuration, "provider_factory_failed"); }
    }
}
/// <summary>Creates each provider lazily once, with explicit per-role chain ordering.</summary>
public sealed class ModelRouter(ProviderRegistry registry, IReadOnlyDictionary<ModelRole, IReadOnlyList<string>> chains,
    Func<IAgentRuntime, IAgentRuntime>? decorate = null)
{
    private readonly ConcurrentDictionary<string, Lazy<IAgentRuntime>> _providers = new(StringComparer.Ordinal);
    /// <summary>Returns one shared decorated provider instance.</summary>
    public IAgentRuntime Runtime(string name) => _providers.GetOrAdd(name, key => new Lazy<IAgentRuntime>(
        () => decorate is null ? registry.Build(key) : decorate(registry.Build(key)), LazyThreadSafetyMode.ExecutionAndPublication)).Value;
    /// <summary>Selects the configured chain for one role.</summary>
    public ProviderChain Chain(ModelRole role) => chains.TryGetValue(role, out var names)
        ? new(names.Select(Runtime).ToArray())
        : throw new ModelException(ModelErrorKind.Configuration, "missing_role_chain");
    /// <summary>Reports all configured providers, not only those already invoked.</summary>
    public IReadOnlyList<ProviderStatus> Statuses() => [.. chains.Values.SelectMany(v => v).Distinct().Select(n => Runtime(n).Status())];
    /// <summary>Reset is for isolated harness scenarios, after all streams have been disposed.</summary>
    public void Reset() => _providers.Clear();
}
/// <summary>Resolves injected definitions without owning agents, prompts, routes or model calculations.</summary>
public sealed class NarrationService(IEnumerable<AgentSpec> definitions, ModelRouter router)
{
    private readonly Dictionary<string, AgentSpec> _specs = BuildSpecs(definitions);
    private static Dictionary<string, AgentSpec> BuildSpecs(IEnumerable<AgentSpec> specs)
    {
        var result = new Dictionary<string, AgentSpec>(StringComparer.Ordinal);
        foreach (var spec in specs)
        {
            if (!result.TryAdd(spec.Name, spec))
            {
                throw new ModelException(ModelErrorKind.Configuration, "duplicate_spec");
            }
        }

        return result;
    }
    /// <summary>All requested definitions must have a configured provider.</summary>
    public bool Available(IEnumerable<string> names) => names.All(n => _specs.TryGetValue(n, out var spec)
        && router.Chain(spec.Role).ReadyFor(n));
    /// <summary>Dispatches an injected definition through its guarded role chain.</summary>
    public IAsyncEnumerable<ModelEvent> StreamAsync(string agent, string prompt, string principal = "anonymous",
        System.Text.Json.JsonElement? trustedFacts = null, CancellationToken cancellationToken = default)
    {
        if (!_specs.TryGetValue(agent, out var spec))
        {
            throw new ModelException(ModelErrorKind.Configuration, "unknown_spec");
        }

        return router.Chain(spec.Role).StreamAsync(new NarrationRequest(spec, prompt, principal, trustedFacts), cancellationToken);
    }
}
