using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Primitives;

namespace TaxCredit.Api.Endpoints.ReadsCalc;

/// <summary>Explicit host routes supersede this feature's defaults regardless of group discovery order.</summary>
internal sealed class ReadEndpointFallbacks(IEndpointRouteBuilder host) : EndpointDataSource, IEndpointRouteBuilder
{
    private readonly List<EndpointDataSource> _sources = [];

    public IServiceProvider ServiceProvider => host.ServiceProvider;
    public ICollection<EndpointDataSource> DataSources => _sources;
    public IApplicationBuilder CreateApplicationBuilder() => host.CreateApplicationBuilder();

    public override IReadOnlyList<Endpoint> Endpoints
    {
        get
        {
            var overrides = host.DataSources.Where(source => !ReferenceEquals(source, this))
                .SelectMany(source => source.Endpoints).OfType<RouteEndpoint>().ToArray();
            return _sources.SelectMany(source => source.Endpoints).Where(endpoint =>
                endpoint is not RouteEndpoint route || !overrides.Any(other => Conflicts(route, other))).ToArray();
        }
    }

    public override IChangeToken GetChangeToken() =>
        new CompositeChangeToken(_sources.Select(source => source.GetChangeToken()).ToArray());

    private static bool Conflicts(RouteEndpoint first, RouteEndpoint second)
    {
        if (!string.Equals(first.RoutePattern.RawText, second.RoutePattern.RawText, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }
        var firstMethods = first.Metadata.GetMetadata<IHttpMethodMetadata>()?.HttpMethods;
        var secondMethods = second.Metadata.GetMetadata<IHttpMethodMetadata>()?.HttpMethods;
        return firstMethods is null || secondMethods is null
            || firstMethods.Intersect(secondMethods, StringComparer.OrdinalIgnoreCase).Any();
    }
}
