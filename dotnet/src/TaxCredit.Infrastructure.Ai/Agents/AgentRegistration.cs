using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Infrastructure.Ai.Agents;

namespace Microsoft.Extensions.DependencyInjection;

/// <summary>Composition binds validated prompt resources without exposing adapter types to endpoint groups.</summary>
public static class AgentRegistration
{
    /// <summary>Keeps the existing provider graph and leaves the production publishing factory an explicit integration.</summary>
    public static IServiceCollection AddTaxCreditPromptAgents(this IServiceCollection services)
    {
        services.TryAddSingleton(AgentRoster.Load());
        services.TryAddSingleton<IAiNarrator, AgentNarrator>();
        return services;
    }
}
