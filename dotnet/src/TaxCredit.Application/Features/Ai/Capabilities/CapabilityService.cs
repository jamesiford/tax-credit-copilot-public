using System.Globalization;
using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>One invocation boundary for transports: resolve, bind targets, validate, dispatch, then enforce lanes.</summary>
public sealed class CapabilityService
{
    private readonly CapabilityCatalog _catalog;
    private readonly IApiPrincipalAccessor _principals;
    private readonly IClientAuthorizer _clients;
    private readonly CapabilityDispatcher _dispatcher;
    private readonly CapabilityOptions _options;
    private readonly IAiTelemetry? _telemetry;

    internal CapabilityService(CapabilityCatalog catalog, IApiPrincipalAccessor principals, IClientAuthorizer clients,
        CapabilityDispatcher dispatcher, CapabilityOptions options, IAiTelemetry? telemetry) =>
        (_catalog, _principals, _clients, _dispatcher, _options, _telemetry) = (catalog, principals, clients, dispatcher, options, telemetry);

    /// <summary>Declared tools remain visible; internal plumbing and debug diagnostics do not.</summary>
    public JsonObject List() => _catalog.List();

    /// <summary>A timeout stops waiting, not a possibly accepted commit; retry a commit with the same key.</summary>
    public async Task<JsonObject> InvokeAsync(string tool, JsonObject args, string? idempotencyKey = null,
        string? confirmationToken = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            if (idempotencyKey?.Length > 200 || confirmationToken?.Length > 500)
            {
                throw CapabilityException.Invalid("Envelope key or token exceeds its allowed length.");
            }
            var spec = _catalog.Resolve(tool);
            var merged = MergeCommitArguments(spec, args, idempotencyKey, confirmationToken);
            var principal = _principals.Current ?? ApiPrincipal.Anonymous;
            foreach (var client in ClientIds(merged).Order())
            {
                if (!await _clients.IsAuthorizedAsync(principal, client, cancellationToken).ConfigureAwait(false))
                {
                    throw new CapabilityException(403, "client_not_authorized", $"not authorized for client {client}");
                }
            }
            CapabilitySchema.Validate(spec["schema"]!.AsObject(), merged);
            var work = Task.Run(() => _dispatcher.InvokeAsync(tool, merged, principal, cancellationToken), CancellationToken.None);
            var result = await work.WaitAsync(_options.Timeout, cancellationToken).ConfigureAwait(false);
            await _dispatcher.CheckLaneAsync(principal, result, cancellationToken).ConfigureAwait(false);
            return result.ToJson();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            var failure = CapabilityFailures.Map(error, tool);
            if (failure.Code == "internal_error")
            {
                _telemetry?.Count("capability_unexpected_error", scope: tool);
            }
            throw failure;
        }
    }

    /// <summary>Outer fields fill omissions, but contradictory fields cannot change the approved request.</summary>
    public static JsonObject MergeCommitArguments(JsonObject spec, JsonObject arguments, string? key, string? token)
    {
        var merged = (JsonObject)arguments.DeepClone();
        if (spec["kind"]!.GetValue<string>() != "write_commit")
        {
            return merged;
        }
        if (!merged.ContainsKey("arguments") && !merged.ContainsKey("idempotency_key") && !merged.ContainsKey("confirmation_token"))
        {
            merged = new JsonObject { ["arguments"] = merged };
        }
        foreach (var (name, value) in new[] { ("idempotency_key", key), ("confirmation_token", token) })
        {
            if (value is null)
            {
                continue;
            }
            if (merged.TryGetPropertyValue(name, out var existing) && !JsonNode.DeepEquals(existing, JsonValue.Create(value)))
            {
                throw CapabilityException.Invalid($"{name} is given twice and the two differ");
            }
            merged[name] = value;
        }
        return merged;
    }

    /// <summary>All selected clients are authorized, including lists inside a batch scope or commit.</summary>
    public static IReadOnlySet<long> ClientIds(JsonObject args)
    {
        var found = new HashSet<long>();
        foreach (var source in new[] { args, args["arguments"] as JsonObject }.OfType<JsonObject>())
        {
            foreach (var key in new[] { "client_id", "account_id" })
            {
                Add(source[key]);
            }
            foreach (var holder in new[] { source, source["scope"] as JsonObject }.OfType<JsonObject>())
            {
                foreach (var key in new[] { "client_ids", "account_ids" })
                {
                    foreach (var value in holder[key] as JsonArray ?? [])
                    {
                        Add(value);
                    }
                }
            }
        }
        return found;

        void Add(JsonNode? value)
        {
            if (CapabilitySchema.IsInteger(value) && long.TryParse(value!.ToJsonString(),
                NumberStyles.Float, CultureInfo.InvariantCulture, out var id))
            {
                found.Add(id);
            }
        }
    }
}

internal static class CapabilityFailures
{
    internal static CapabilityException Map(Exception error, string tool) => error switch
    {
        CapabilityException refusal => refusal,
        ApiAuthException refusal => new CapabilityException(refusal.StatusCode, "not_authorized", refusal.Message),
        SourceFailureException => new CapabilityException(503, "data_source_unavailable", "The source data is unavailable."),
        TimeoutException => new CapabilityException(504, "timeout", $"{tool} did not finish in time; a commit may still land. Retry with the same idempotency key.", true),
        ArgumentException => new CapabilityException(422, "rejected", "The capability rejected the arguments."),
        _ => QueryFailure(error) ?? new CapabilityException(500, "internal_error", "the capability failed unexpectedly", true, innerException: error),
    };

    private static CapabilityException? QueryFailure(Exception error)
    {
        // W1 exposes Code on its query refusal but currently locates that type behind the port.
        var code = error.GetType().GetProperty("Code")?.GetValue(error) as string;
        var status = code switch
        {
            "employee_level_not_allowed" => 403,
            "query_timeout" => 504,
            "query_budget_exceeded" => 429,
            "query_busy" or "data_source_unavailable" or "data_source_disabled" => 503,
            "query_failed" => 502,
            "unknown_dataset" or "unknown_column" or "blocked_column" or "column_not_listable" or
                "malformed_spec" or "invalid_grouping" or "duplicate_label" or "invalid_order" or
                "invalid_aggregation" or "method_not_applicable" or "tax_year_out_of_range" or "empty_query" => 422,
            _ => 0,
        };
        return status == 0 ? null : new CapabilityException(status, code!, "The governed query was refused.",
            code is "query_timeout" or "query_budget_exceeded" or "query_busy" or "query_failed");
    }
}
