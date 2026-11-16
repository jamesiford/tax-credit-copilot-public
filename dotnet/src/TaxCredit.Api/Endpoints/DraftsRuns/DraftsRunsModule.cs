using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.DraftsRuns;

/// <summary>Feature-owned registrations are discovered before host construction.</summary>
public sealed class DraftsRunsModule : IFeatureModule
{
    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        services.AddScoped<BatchPlanner>();
        services.AddScoped<BatchSelection>();
        services.AddScoped<BatchAccess>();
        services.AddScoped<DraftLifecycle>();
        services.AddScoped<DraftValidation>();
        services.AddScoped<DraftCustomerData>();
        services.AddScoped<SyntheticPreviewSample>();
        services.AddScoped<TaxCredit.Domain.Programs.PackValidator>();
        RegisterScopedHandlers(services);
    }

    private static void RegisterScopedHandlers(IServiceCollection services)
    {
        foreach (var type in typeof(BatchRequest).Assembly.GetTypes().Where(t => t.Namespace == typeof(BatchRequest).Namespace && t is { IsClass: true, IsAbstract: false }))
        {
            foreach (var contract in type.GetInterfaces().Where(i => i.IsGenericType && i.GetGenericTypeDefinition() == typeof(IRequestHandler<,>)))
            {
                services.AddTransient(type);
                var wrapper = typeof(RequestScopeHandler<,>).MakeGenericType(contract.GenericTypeArguments);
                services.AddTransient(contract, provider => Activator.CreateInstance(wrapper, provider.GetRequiredService<IServiceScopeFactory>(), type)!);
            }
        }
    }

    // The inherited singleton mediator resolves from its root provider. Keep feature source/connection lifetimes per dispatch.
    private sealed class RequestScopeHandler<TRequest, TResponse>(IServiceScopeFactory factory, Type handlerType) : IRequestHandler<TRequest, TResponse>
        where TRequest : IRequest<TResponse>
    {
        public async ValueTask<TResponse> Handle(TRequest request, CancellationToken cancellationToken)
        {
            using var scope = factory.CreateScope();
            var handler = (IRequestHandler<TRequest, TResponse>)scope.ServiceProvider.GetRequiredService(handlerType);
            return await handler.Handle(request, cancellationToken).ConfigureAwait(false);
        }
    }
}
