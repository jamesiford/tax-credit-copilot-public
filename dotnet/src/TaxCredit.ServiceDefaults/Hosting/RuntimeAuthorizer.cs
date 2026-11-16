using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>The synchronous mediator policy uses the same person entitlement as HTTP, never an agent's grant.</summary>
internal sealed class RuntimeAuthorizer(IApiPrincipalAccessor principals, IWriterPolicy writers) : IAuthorizer
{
    public bool IsEntitled(Policy policy)
    {
        if (policy == Policy.Open) { return true; }
        if (policy != Policy.Writer || principals.Current is not { } principal) { return false; }
        try
        {
            writers.CheckAsync(principal, principal.Actor, true).AsTask().GetAwaiter().GetResult();
            return true;
        }
        catch (AuthRefusalException) { return false; }
    }
}
