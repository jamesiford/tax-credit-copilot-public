using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Routing;
using TaxCredit.Api.Contract;
using TaxCredit.Api.Hosting;
using TaxCredit.Api.Wire;

namespace TaxCredit.Api.Endpoints;

/// <summary>Discovers groups before filling only unclaimed method/template pairs with honest 501s.</summary>
public static class EndpointRegistration
{
    /// <summary>Discovers groups from the host assembly and registers the complete decided surface.</summary>
    public static void MapEndpointGroups(this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        foreach (var type in endpoints.ServiceProvider.GetRequiredService<FeatureDiscovery>().Types
            .Where(t => t is { IsClass: true, IsAbstract: false } && typeof(IEndpointGroup).IsAssignableFrom(t))
            .OrderBy(t => t.FullName, StringComparer.Ordinal))
        {
            var group = (IEndpointGroup)ActivatorUtilities.CreateInstance(endpoints.ServiceProvider, type);
            group.Map(endpoints);
        }

        endpoints.MapUnclaimedOperations();
    }

    /// <summary>Call after real groups are mapped; method metadata prevents ambiguity even on shared paths.</summary>
    public static void MapUnclaimedOperations(this IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var table = endpoints.ServiceProvider.GetRequiredService<RouteTable>();
        var claimed = endpoints.DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>().ToArray();
        foreach (var operation in table.Operations)
        {
            var real = claimed.Where(e => string.Equals(e.RoutePattern.RawText, operation.Path, StringComparison.OrdinalIgnoreCase))
                .FirstOrDefault(e => e.Metadata.GetMetadata<IHttpMethodMetadata>() is not { } methods
                    || methods.HttpMethods.Contains(operation.Method, StringComparer.OrdinalIgnoreCase));
            if (real is not null)
            {
                continue;
            }

            endpoints.MapMethods(operation.Path, [operation.Method], () => ApiErrors.Detail(
                StatusCodes.Status501NotImplemented, $"Operation not implemented: {operation.Method} {operation.Path}"))
                .WithMetadata(operation)
                .WithName("stub." + operation.Method + "." + operation.Name);
        }

    }
}
