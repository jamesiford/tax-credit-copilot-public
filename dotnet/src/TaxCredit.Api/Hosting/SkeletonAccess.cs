using TaxCredit.Application.Ports;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Hosting;

/// <summary>Only an explicit local mode or hermetic startup may bypass auth; a missing adapter fails closed.</summary>
public sealed class SkeletonAccess(IRuntimeConfiguration configuration, IConfiguration startup) : IApiAccess
{
    /// <inheritdoc />
    public ValueTask<ApiAccessDecision> Check(ApiAccessRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var mode = configuration.Get("AUTH_MODE");
        if (mode != "entra" && startup["TCC_CONTRACT_HOOKS"] == "1"
            || mode == "none" && configuration.Get("ENVIRONMENT") == "local")
        {
            return ValueTask.FromResult(new ApiAccessDecision(true));
        }

        if (!request.Headers.TryGetValue("Authorization", out var bearer)
            || !bearer.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)
            || string.IsNullOrWhiteSpace(bearer[7..]))
        {
            return ValueTask.FromResult(new ApiAccessDecision(false, 401, "no bearer token", true));
        }

        return ValueTask.FromResult(new ApiAccessDecision(false, 503,
            "Authentication adapter is not installed; signed-in requests cannot be authorized."));
    }
}
