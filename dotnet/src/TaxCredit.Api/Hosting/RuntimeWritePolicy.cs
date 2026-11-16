using TaxCredit.Application.Ports;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.Api.Hosting;

internal static class RuntimeWritePolicy
{
    internal static bool RequiresWriter(ApiAccessRequest request)
    {
        if (request.Method == "GET" && request.Path.StartsWith("/api/rules/ingested/", StringComparison.Ordinal)
            && request.Path.EndsWith("/refresh", StringComparison.Ordinal)) { return true; }
        if (!RoutePolicy.RequiresWriterDecision(request.Method)) { return false; }
        if (request.Method != "POST") { return true; }
        return request.Path is not ("/api/chat" or "/api/summary" or "/api/employee/drill" or "/api/workspace/employee"
            or "/api/workspace/source/search")
            && !request.Path.StartsWith("/api/capabilities/", StringComparison.Ordinal)
            && !request.Path.StartsWith("/api/simulate/", StringComparison.Ordinal);
    }
}
