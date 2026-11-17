using Microsoft.Extensions.DependencyInjection;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Each operation owns its adapters even when the shared mediator resolves a handler from its root provider.</summary>
internal static class ReadHandlerScope
{
    internal static object Execute<TService>(IServiceScopeFactory scopes, Func<TService, object> operation)
        where TService : notnull
    {
        using var scope = scopes.CreateScope();
        return operation(scope.ServiceProvider.GetRequiredService<TService>());
    }
}
