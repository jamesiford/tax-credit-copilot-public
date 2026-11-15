using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Rules;

/// <summary>
/// Wiring of the rule library (Python <c>tools/credit_math.py</c> and friends). The library and its ports (<see cref="IRulePackSource"/>,
/// <see cref="IIngestedOneZeroSource"/>, <see cref="IProgramWageSource"/>) live in the Domain because the resolution rules are pure; the adapters that read
/// the rules folder live in Infrastructure, and this is where the two meet.
/// </summary>
public static class RuleLibraryRegistration
{
    /// <summary>Registers one <see cref="RuleLibrary"/> over whichever ports are registered; only <see cref="IRulePackSource"/> is required.</summary>
    /// <param name="services">The container.</param>
    /// <returns>The same container, for chaining.</returns>
    public static IServiceCollection AddRuleLibrary(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.TryAddSingleton(sp => new RuleLibrary(
            sp.GetRequiredService<IRulePackSource>(),
            sp.GetService<IIngestedOneZeroSource>(),
            sp.GetService<IProgramWageSource>()));
        return services;
    }

    /// <summary>
    /// Registers one <see cref="PackValidator"/> (Python <c>tools/pack_validation.py</c>) over <see cref="IRulePackSource"/>, <see cref="IJsonSchemaValidator"/> and the
    /// registered <see cref="RuleLibrary"/>; call <see cref="AddRuleLibrary"/> first.
    /// </summary>
    /// <param name="services">The container.</param>
    /// <returns>The same container, for chaining.</returns>
    public static IServiceCollection AddPackValidator(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.TryAddSingleton(sp => new PackValidator(
            sp.GetRequiredService<IRulePackSource>(),
            sp.GetRequiredService<IJsonSchemaValidator>(),
            sp.GetRequiredService<RuleLibrary>()));
        return services;
    }
}
