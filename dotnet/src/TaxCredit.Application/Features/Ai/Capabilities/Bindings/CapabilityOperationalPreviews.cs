using System.Text.Json.Nodes;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Operational previews read stored evidence and run the owner's dry-run query only.</summary>
public sealed class CapabilityOperationalPreviews(IMediator mediator, IGoldReadPort gold,
    IArtifactRepository artifacts, IManualOverrideRepository overrides, ProgramDefaults defaults)
{
    internal async Task<JsonObject> BaseYear(JsonObject a, CancellationToken token)
    {
        var client = Client(a);
        var unit = Text(a, "unit_id")!;
        var chosen = CapabilityJson.Integer(a["base_year"]!);
        var state = defaults.LocationState(client, unit, Text(a, "state"), Text(a, "program_code"));
        var (_, program) = defaults.ResolveProgram(client, state, Text(a, "program_code"), null);
        if (program is null) { throw CapabilityException.Invalid("No program maps to the location's state."); }
        using var scope = gold.Scope();
        if (gold.LatestRun(client) is null) { throw NotCalculated("This client has no calculated run to change."); }
        var rows = UnitSeries.Load(gold, client, unit, "min_max", program);
        var saved = overrides.BaseYears(client, program).TryGetValue(unit, out var value) ? value : (long?)null;
        var repriced = Object(await mediator.Send(new RebaseUnitQuery(client, unit, chosen, State: state, ProgramCode: program), token).ConfigureAwait(false));
        return Preview(new JsonObject { ["base_year"] = saved ?? UnitSeries.Inferred(rows) },
            Select(repriced, "base_year", "total_annual_credit_usd", "run_total_annual_credit_usd", "delta_annual_credit_usd")!);
    }

    internal JsonObject Package(JsonObject a)
    {
        using var scope = gold.Scope();
        var run = gold.LatestRun(Client(a)) ?? throw NotCalculated("This client has no completed calculation run to package.");
        var live = artifacts.Live(Client(a), "claim_package", Year(a));
        var earlier = live.Count > 0 ? live[0] : null;
        return Preview(earlier is null ? null : new JsonObject { ["file_name"] = earlier.FileName, ["run_id"] = earlier.RunId },
            new JsonObject { ["run_id"] = run["run_id"]?.ToString(), ["tax_year"] = Year(a), ["sheets"] = string.Join(", ", PackageColumns.Names) });
    }

    internal async Task<JsonObject> Batch(JsonObject a, CancellationToken token)
    {
        var body = BatchBody(a);
        var result = Object(await mediator.Send(new PreviewBatchQuery(Body(body)), token).ConfigureAwait(false));
        var preview = result["preview"]!.AsObject();
        if (preview["over_size_limit"]?.GetValue<bool>() == true)
        {
            throw CapabilityException.Invalid($"This selects {preview["items"]} runs, over the limit of {preview["max_items"]}.");
        }
        if (preview["requires_confirmation"]?.GetValue<bool>() == true &&
            !JsonNode.DeepEquals(a["confirm_items"], preview["items"]))
        {
            throw CapabilityException.Invalid($"The person must confirm the count. Prepare again with confirm_items={preview["items"]}.");
        }
        var years = preview["years"] is JsonArray array ? string.Join(", ", array.Select(year => year!.ToString())) : preview["years"]!.ToString();
        var after = new JsonObject
        {
            ["kind"] = preview["kind"]!.GetValue<string>().Replace('_', ' '),
            ["clients"] = preview["clients"]?.DeepClone(),
            ["runs to queue"] = preview["items"]?.DeepClone(),
            ["tax years"] = years,
            ["never calculated"] = preview["never_run"]?.DeepClone(),
            ["may be skipped (an upper bound, decided as each run starts)"] = preview["skip_candidates_upper_bound"]?.DeepClone(),
            ["unavailable clients"] = preview["unavailable"]!.AsArray().Count,
            ["skip unchanged clients"] = preview["skip_unchanged"]?.GetValue<bool>() == true && preview["force"]?.GetValue<bool>() != true ? "yes" : "no (every item runs)",
            ["programs"] = string.Join(", ", preview["programs"]!.AsObject().OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair => $"{pair.Key}: {pair.Value}")),
            ["first clients"] = string.Join(", ", preview["first_items"]!.AsArray().Take(5).Select(item => (item!["client_name"] ?? item["client_id"])!.ToString())),
        };
        return Preview(null, after);
    }

    internal static JsonObject BatchBody(JsonObject arguments)
    {
        var body = (JsonObject)arguments.DeepClone();
        var scope = body["scope"]!.AsObject();
        scope["client_ids"] = scope["account_ids"]?.DeepClone() ?? new JsonArray();
        scope.Remove("account_ids");
        if (body["options"] is JsonObject options)
        {
            foreach (var pair in options) { body[pair.Key] = pair.Value?.DeepClone(); }
        }
        body.Remove("options");
        return body;
    }
}
