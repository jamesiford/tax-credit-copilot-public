using TaxCredit.Application.Ports;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.Api.Hosting;

/// <summary>Authentication returns identity explicitly; an AsyncLocal written below an await is not request propagation.</summary>
public sealed class RuntimeAccess(IApiTrustService trust, IWriterPolicy writers, IApiRateLimiter limiter) : IApiAccess
{
    /// <inheritdoc />
    public async ValueTask<ApiAccessDecision> Check(ApiAccessRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var principal = await trust.AuthenticateAsync(request.Path, request.Headers.GetValueOrDefault("Authorization"),
            request.Headers.GetValueOrDefault("X-TCC-Acting-User"), cancellationToken).ConfigureAwait(false);
        var clients = ClientSelection.Extract(request.RouteValues.Select(p => KeyValuePair.Create<string, object?>(p.Key, p.Value)),
            request.Query.SelectMany(p => p.Value.Select(v => KeyValuePair.Create<string, string?>(p.Key, v))), request.Body);
        await trust.AuthorizeRequestAsync(principal, request.Method, request.Path, clients, cancellationToken).ConfigureAwait(false);
        if (principal.IsAgent && RoutePolicy.IsPersonOnlyRead(request.Method, request.Path))
        {
            throw new AuthRefusalException(403, "person_required", "This read requires a person.");
        }

        var write = RuntimeWritePolicy.RequiresWriter(request) && !PreservedWrite(request);
        var actor = request.Body is { ValueKind: System.Text.Json.JsonValueKind.Object } body
            && body.TryGetProperty("actor", out var value) && value.ValueKind == System.Text.Json.JsonValueKind.String ? value.GetString() : null;
        await writers.CheckAsync(principal, principal.Attributed(actor), write, cancellationToken).ConfigureAwait(false);
        if (RoutePolicy.RateLimitKind(request.Method, request.Path) is { } kind)
        {
            var decision = limiter.Check(kind, principal);
            if (!decision.Allowed) { throw new RateRefusalException(decision); }
        }

        return new ApiAccessDecision(true, Principal: principal);
    }

    // F-14 valid-request outcomes are protected by the supplied policy, not accidental omissions.
    private static bool PreservedWrite(ApiAccessRequest request) =>
        request.Method == "POST" && (request.Path == "/api/claims/assess"
        || request.Path.StartsWith("/api/v2/clients/", StringComparison.Ordinal) && request.Path.EndsWith("/runs", StringComparison.Ordinal)
        || request.Path.StartsWith("/api/rules/", StringComparison.Ordinal) && request.Path.EndsWith("/verify", StringComparison.Ordinal)
        || request.Path == "/api/v2/run-batches" && request.Body is { ValueKind: System.Text.Json.JsonValueKind.Object } body
            && body.TryGetProperty("dry_run", out var dry) && dry.ValueKind == System.Text.Json.JsonValueKind.True);
}

/// <summary>Rate decisions retain the adapter's retry interval without flattening them into authorization refusals.</summary>
public sealed class RateRefusalException(RateLimitDecision decision) : Exception("Rate limit exceeded.")
{
    /// <summary>The W1 limiter's signed-caller decision.</summary>
    public RateLimitDecision Decision { get; } = decision;
}
