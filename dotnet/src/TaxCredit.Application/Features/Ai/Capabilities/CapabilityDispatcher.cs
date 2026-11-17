using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed class CapabilityDispatcher(CapabilityDirectReads direct, CapabilityData data, CapabilityWrites writes,
    ICapabilityReadBridge bridge, IWriterEntitlement writers, CapabilityCatalog catalog)
{
    internal async Task<CapabilityResult> InvokeAsync(string tool, JsonObject args, ApiPrincipal principal, CancellationToken cancellationToken)
    {
        if (tool.EndsWith("_prepare", StringComparison.Ordinal) || tool.EndsWith("_commit", StringComparison.Ordinal))
        {
            return await writes.InvokeAsync(tool, args, principal, cancellationToken).ConfigureAwait(false);
        }
        args = Defaults(tool, args);
        if (tool is "data_catalog" or "data_query" or "data_distinct_values")
        {
            return await data.InvokeAsync(tool, args, principal, cancellationToken).ConfigureAwait(false);
        }
        var result = await direct.TryInvokeAsync(tool, args, principal, cancellationToken).ConfigureAwait(false);
        if (result is not null)
        {
            return result;
        }

        var read = await bridge.ReadAsync(tool, args, principal, cancellationToken).ConfigureAwait(false);
        return CapabilityRender.Render(tool, read);
    }

    private JsonObject Defaults(string tool, JsonObject args)
    {
        var merged = (JsonObject)args.DeepClone();
        foreach (var (name, field) in catalog.Resolve(tool)["schema"]!["properties"]!.AsObject())
        {
            if (!merged.ContainsKey(name) && field?["default"] is { } value)
            {
                merged[name] = value.DeepClone();
            }
        }
        return merged;
    }

    internal async Task CheckLaneAsync(ApiPrincipal principal, CapabilityResult result, CancellationToken cancellationToken)
    {
        if (result.HasUserLane && !await CanReadPeopleAsync(principal, cancellationToken).ConfigureAwait(false))
        {
            throw new CapabilityException(403, "employee_level_not_allowed",
                "Employee-level rows are available only in an entitled first-party channel or to a writer. Ask for an aggregate instead.");
        }
    }

    private async Task<bool> CanReadPeopleAsync(ApiPrincipal principal, CancellationToken cancellationToken) =>
        principal.IsAgent && principal.ActingFor?.IsFirstParty == true ||
        principal.EffectiveOid is { Length: > 0 } oid && await writers.IsWriterAsync(oid, cancellationToken).ConfigureAwait(false);
}
