using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Infrastructure.Ai.Telemetry;

namespace TaxCredit.Infrastructure.Ai;

/// <summary>Owned composition helpers; the root supplies transports and exporter registration.</summary>
public static class AiRegistration
{
    /// <summary>The root supplies factories and definitions; registering never invokes a live provider.</summary>
    public static IServiceCollection AddTaxCreditAi(this IServiceCollection services, ProviderRegistry providers,
        IReadOnlyDictionary<ModelRole, IReadOnlyList<string>> chains, IEnumerable<AgentSpec> definitions,
        IAiTelemetry telemetry, AiRuntimeOptions? options = null, TimeProvider? clock = null)
    {
        options ??= new();
        options.Resilience.Validate();
        var budget = new InMemoryTokenBudget(options.GlobalDailyTokens, options.PrincipalDailyTokens, clock);
        var router = new ModelRouter(providers, chains,
            runtime => BuildRuntime(runtime, budget, telemetry, options, clock));
        services.AddSingleton<ITokenBudget>(budget);
        services.AddSingleton<IAiTelemetry>(telemetry);
        services.AddSingleton(router);
        services.AddSingleton(new NarrationService(definitions, router));
        return services;
    }
    /// <summary>Composes observation, guards, bulkhead, breaker, retry, event-gap timeout and per-attempt accounting.</summary>
    public static IAgentRuntime BuildRuntime(IAgentRuntime provider, ITokenBudget budget, IAiTelemetry telemetry,
        AiRuntimeOptions options, TimeProvider? clock = null, Func<double>? jitter = null)
    {
        var p = options.Resilience;
        p.Validate();
        IAgentRuntime runtime = new AccountedRuntime(provider, budget, telemetry);
        runtime = new TimeoutRuntime(runtime, p.Gap, clock);
        runtime = new RetryRuntime(runtime, p, clock, jitter, telemetry);
        runtime = new BreakerRuntime(runtime, new CircuitBreaker(p.FailureThreshold, p.BreakerReset, clock), telemetry);
        runtime = new BulkheadRuntime(runtime, p.MaxConcurrency, telemetry);
        runtime = new GuardedRuntime(runtime, new EgressGuard(options.Egress), options.InjectionGuard ? new PromptInjectionGuard() : null, telemetry);
        return new ObservedRuntime(runtime, telemetry);
    }
}
/// <summary>Guard and resilience policy supplied by the host.</summary>
public sealed record AiRuntimeOptions
{
    /// <summary>Bounded provider execution controls.</summary>
    public ResilienceSettings Resilience { get; init; } = new();
    /// <summary>External-provider egress policy.</summary>
    public EgressPolicy Egress { get; init; } = EgressPolicy.AllowAll;
    /// <summary>Enables normalized injection screening.</summary>
    public bool InjectionGuard { get; init; } = true;
    /// <summary>Optional overall UTC-day token ceiling.</summary>
    public long? GlobalDailyTokens { get; init; }
    /// <summary>Optional per-principal UTC-day token ceiling.</summary>
    public long? PrincipalDailyTokens { get; init; }
}
