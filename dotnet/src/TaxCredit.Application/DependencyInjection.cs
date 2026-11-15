using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Rules;

namespace TaxCredit.Application;

/// <summary>Composition of the application layer. Adapters for the ports are registered by Infrastructure.</summary>
public static class DependencyInjection
{
    /// <summary>Registers the mediator, the pipeline (Authorization, Validation, Audit) and every handler in this assembly.</summary>
    /// <param name="services">The container.</param>
    /// <returns>The same container, for chaining.</returns>
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.TryAddSingleton<IMediator, Mediator>();
        services.AddRuleLibrary();
        // Registration order is execution order: Audit is outermost so that refusals and validation failures are
        // recorded too, then Authorization, Validation, and finally the handler.
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(AuditBehavior<,>));
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(AuthorizationBehavior<,>));
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(ValidationBehavior<,>));

        var handlerInterface = typeof(IRequestHandler<,>);
        foreach (var type in typeof(DependencyInjection).Assembly.GetTypes().Where(t => t is { IsClass: true, IsAbstract: false }))
        {
            foreach (var i in type.GetInterfaces().Where(i => i.IsGenericType && i.GetGenericTypeDefinition() == handlerInterface))
            {
                services.AddTransient(i, type);
            }
        }

        return services;
    }
}
