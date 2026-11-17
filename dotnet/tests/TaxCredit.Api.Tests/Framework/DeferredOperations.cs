using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Routing;
using TaxCredit.Api.Contract;

namespace TaxCredit.Api.Tests.Framework;

internal static class DeferredOperations
{
    internal static async Task<(RouteOperation Replaced, RouteOperation Remaining)> Pair()
    {
        await using var host = await TestHost.Start();
        var deferred = ((IEndpointRouteBuilder)host.App).DataSources.SelectMany(s => s.Endpoints)
            .OfType<RouteEndpoint>()
            .Where(e => e.Metadata.GetMetadata<IEndpointNameMetadata>()?.EndpointName?.StartsWith("stub.", StringComparison.Ordinal) == true)
            .Select(e => e.Metadata.GetMetadata<RouteOperation>()!)
            .Where(o => o.Method == "GET" && !o.Path.Contains('{'))
            .OrderBy(o => o.Path, StringComparer.Ordinal).Take(2).ToArray();
        if (deferred.Length < 2)
        {
            throw Xunit.Sdk.SkipException.ForSkip("Fewer than two callable GET stubs remain in the discovered route table.");
        }
        return (deferred[0], deferred[1]);
    }

    internal static void AssertSingle(IEndpointRouteBuilder host, RouteOperation operation) =>
        Assert.Single(host.DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>(), e =>
            e.RoutePattern.RawText == operation.Path
            && e.Metadata.GetMetadata<IHttpMethodMetadata>()!.HttpMethods.Contains(operation.Method));
}
