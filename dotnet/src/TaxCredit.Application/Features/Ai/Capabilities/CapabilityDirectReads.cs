using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed class CapabilityDirectReads(IClaimRepository claims, AiClientBook source, IGoldReadPort gold, IClientAuthorizer authorizer)
{
    internal async Task<CapabilityResult?> TryInvokeAsync(string tool, JsonObject args, ApiPrincipal principal,
        CancellationToken cancellationToken) => tool switch
        {
            "client_situation" => Situation(args),
            "claim_cell_history" => History(args),
            "client_trend" => Trend(args),
            "client_resolve" => await ResolveAsync(args, principal, cancellationToken).ConfigureAwait(false),
            _ => null,
        };

    private CapabilityResult Situation(JsonObject args)
    {
        var client = CapabilityJson.Integer(args["client_id"]!);
        var year = args["year"] is { } selected ? CapabilityJson.Integer(selected) : (long?)null;
        var cells = claims.Coverage(client, taxYears: year is null ? null : [year.Value]);
        var facts = new JsonObject { ["client_id"] = client, ["tax_year"] = year, ["assessed"] = cells.Count > 0 };
        if (cells.Count == 0)
        {
            facts["message"] = $"No assessment has been run for this client{(year is null ? "" : $" in TY{year}")}. There is no figure to report — that is not the same as zero.";
        }
        else
        {
            foreach (var pair in CapabilityResult.Object(CoverageSituation.Situation(cells)))
            {
                facts[pair.Key] = pair.Value?.DeepClone();
            }
        }
        facts["client_name"] = source.Entries().FirstOrDefault(account => account.AccountId == client)?.Name;
        return CapabilityRender.Render("client_situation", new CapabilityRead(facts,
            CapabilityResult.Evidence(source: "recorded claims; no run")));
    }

    private CapabilityResult History(JsonObject args)
    {
        var client = CapabilityJson.Integer(args["client_id"]!);
        var program = args["program_code"]!.GetValue<string>().ToUpperInvariant();
        var year = CapabilityJson.Integer(args["tax_year"]!);
        var current = claims.Current(client, program, year)
            ?? throw new CapabilityException(409, "not_calculated", "No claim has been recorded for this client, programme and year.");
        var history = claims.History(client, program, year);
        var facts = new JsonObject
        {
            ["current"] = CapabilityResult.Object(current.ToDict()),
            ["history"] = new JsonArray(history.Select(entry => (JsonNode)CapabilityResult.Object(entry.ToDict())).ToArray()),
        };
        return CapabilityRender.Render("claim_cell_history", new CapabilityRead(facts,
            CapabilityResult.Evidence(Text(facts["current"], "identified_run_id"), Text(facts["current"], "rule_pack_version"),
                Text(facts["current"], "assumption_set_id"), source: "recorded claims")));
    }

    private CapabilityResult Trend(JsonObject args)
    {
        var client = CapabilityJson.Integer(args["client_id"]!);
        var program = args["program_code"]?.GetValue<string>();
        var series = CapabilityResult.Object(gold.ClientYearSeries(client, "pay_period", program));
        var years = series["years"]!.AsArray();
        var facts = new JsonObject { ["calculated"] = years.Count != 0, ["client_id"] = client, ["method"] = "pay_period" };
        if (years.Count != 0)
        {
            var baseline = years.FirstOrDefault(row => row!["is_base_year"]?.GetValue<bool>() == true)?["tax_year"]?.GetValue<int>();
            var after = years.Where(row => baseline is null || row!["tax_year"]!.GetValue<int>() > baseline).ToArray();
            facts["base_tax_year"] = baseline;
            facts["years"] = years.DeepClone();
            facts["years_held"] = years.Count;
            facts["years_after_base"] = after.Length;
            facts["eligible_every_year_since_base"] = after.Length == 0 ? null : after.All(row => row!["eligible_employees"]!.GetValue<long>() > 0);
            facts["years_with_no_eligible_employees"] = new JsonArray(after.Where(row => row!["eligible_employees"]!.GetValue<long>() == 0)
                .Select(row => row!["tax_year"]!.DeepClone()).ToArray());
            facts["note"] = "Years absent from this list were not reached by the run. They carry no figure, which is not the same as a zero. Where `eligible_every_year_since_base` is null there is no year after the base year to judge — say so rather than reporting a verdict.";
        }
        if (!string.IsNullOrEmpty(program))
        {
            facts["program_code"] = program.Trim().ToUpperInvariant();
        }
        return CapabilityRender.Render("client_trend", new CapabilityRead(facts, RunEvidence(series["run"], "tcc_gold")));
    }

    private async Task<CapabilityResult> ResolveAsync(JsonObject args, ApiPrincipal principal, CancellationToken cancellationToken)
    {
        var accounts = new List<SourceAccount>();
        foreach (var account in source.Entries())
        {
            if (await authorizer.IsAuthorizedAsync(principal, account.AccountId, cancellationToken).ConfigureAwait(false))
            {
                accounts.Add(account);
            }
        }
        if (accounts.Count == 0)
        {
            throw new CapabilityException(404, "client_not_found", "The client book could not be read, so no client can be resolved.");
        }
        return CapabilityClientResolver.Resolve(accounts, args);
    }

    internal static JsonObject RunEvidence(JsonNode? run, string source) => CapabilityResult.Evidence(
        Text(run, "run_id"), Text(run, "rule_pack_version"),
        string.Join(" + ", new[] { Text(run, "step1_assumption_set_id"), Text(run, "onezero_assumption_set_id") }
            .OfType<string>().Where(value => value.Length > 0)) is { Length: > 0 } assumptions ? assumptions : null,
        source: source);

    internal static string? Text(JsonNode? node, string key) => node?[key]?.GetValue<string>();
}
