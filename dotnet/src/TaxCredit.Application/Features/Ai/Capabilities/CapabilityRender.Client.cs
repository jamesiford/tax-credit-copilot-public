using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static partial class CapabilityRender
{
    private static CapabilityResult Situation(CapabilityRead read)
    {
        var facts = read.Facts;
        var name = facts["client_name"] is null ? $"Account {facts["client_id"]}" : T(facts["client_name"]);
        var blocks = new JsonArray(Block("heading", name));
        if (!B(facts["assessed"]))
        {
            blocks.Add(Block("paragraph", T(facts["message"])));
        }
        else
        {
            blocks.Add(Block("paragraph", $"{F(facts["cells"], "count")} recorded cells. Identified credit: {F(facts["identified_usd"], "money")}."));
            // JSON wire ordering is free; the displayed rows still follow the domain's named band ranking.
            var bands = BandNames.Keys.Where(band => band != "unavailable");
            blocks.Add(Table(["Reason", "Programme", "Tax year", "Identified", "Jobs margin"],
                bands.SelectMany(band => A(facts["by_band"]?[band]).Select(cell => new[]
                {
                    BandNames[band], T(cell!["program_code"]), F(cell["tax_year"], "year"),
                    F(cell["identified_usd"], "money"), F(cell["jobs_margin"]),
                }))));
        }
        return new CapabilityResult("client_situation", facts)
        {
            Blocks = blocks,
            Provenance = Evidence(source: "recorded claims; no run"),
            Warnings = B(facts["claimed_is_unverified"]) ?
                ["The claimed side of this book is an unverified assertion; do not read recoverable or exposure figures as findings against a filed return."] : [],
        };
    }

    private static CapabilityResult Eligibility(CapabilityRead read)
    {
        var facts = read.Facts;
        var snapshot = facts["snapshot"]!;
        var credit = facts["credit"]!;
        JsonArray blocks;
        if (!B(snapshot["calculated"]))
        {
            blocks = [Block("paragraph", T(snapshot["note"]))];
        }
        else if (B(credit["no_state_pack"]))
        {
            blocks = [Block("paragraph", T(credit["message"]))];
        }
        else
        {
            blocks =
            [
                Block("heading", $"{T(credit["credit_name"])} · TY{F(snapshot["selected_tax_year"], "year")}"),
                Table(["Measure", "Value"], new (string Label, string Key, string Format)[]
                {
                    ("Average headcount", "average_headcount", "headcount"),
                    ("Prior-year average headcount", "prior_period_average_headcount", "headcount"),
                    ("Qualifying jobs", "qualifying_jobs", "headcount"),
                    ("Annual credit", "annual_credit_usd", "money"),
                    ("Lifetime credit", "lifetime_credit_usd", "money"),
                    ("Benefit period (years)", "benefit_period_years", "count"),
                }.Select(field => new[] { field.Label, F(credit[field.Key], field.Format) })),
                Block("paragraph", $"Citation: {T(credit["citation"])}"),
            ];
        }
        return new CapabilityResult("client_eligibility", facts) { Blocks = blocks };
    }

    private static CapabilityResult Trend(CapabilityRead read)
    {
        var facts = read.Facts;
        if (!B(facts["calculated"]))
        {
            return new CapabilityResult("client_trend", facts)
            {
                Blocks = [Block("paragraph", "No calculated run holds any year for this client. That is not a zero.")],
            };
        }
        var verdict = facts["eligible_every_year_since_base"];
        var line = verdict is null ? "There is no year after the base year to judge." :
            B(verdict) ? "Eligible employees were found in every year since the base year." :
            $"No eligible employees were found in: {string.Join(", ", A(facts["years_with_no_eligible_employees"]).Select(year => F(year, "year")))}.";
        return new CapabilityResult("client_trend", facts)
        {
            Blocks =
            [
                Table(["Tax year", "Average headcount", "Eligible", "Evaluated", "Annual credit", ""],
                    A(facts["years"]).Select(year => new[] { F(year!["tax_year"], "year"),
                        F(year["annual_average"], "headcount"), F(year["eligible_employees"], "count"),
                        F(year["employees_evaluated"], "count"), F(year["annual_credit_usd"], "money"),
                        B(year["is_base_year"]) ? "Base year" : "" })),
                Block("paragraph", line),
            ],
        };
    }

    private static CapabilityResult Risk(CapabilityRead read)
    {
        var facts = read.Facts;
        var text = !B(facts["calculated"])
            ? T(facts["declined"] ?? JsonValue.Create($"No calculated run holds TY{F(facts["tax_year"], "year")} for this client. That is not a zero."))
            : $"{F(facts["within_band"], "count")} of {F(facts["eligible"], "count")} counted employees sit within {F(facts["band_weekly_hours"])} weekly hours of a floor: {F(facts["binding_floors"]!["hours"], "count")} bind on hours and {F(facts["binding_floors"]!["wages"], "count")} on wages. Jobs at risk: {F(facts["jobs_at_risk"], "headcount")}.";
        var blocks = new JsonArray(Block("paragraph", text));
        if (B(facts["calculated"]))
        {
            blocks.Add(Block("paragraph", T(facts["method_note"])));
        }
        return new CapabilityResult("client_at_risk", facts) { Blocks = blocks };
    }

    private static CapabilityResult Discovery(CapabilityRead read)
    {
        var facts = read.Facts;
        var hits = A(facts["hits"]);
        var blocks = new JsonArray(Block("paragraph", hits.Count == 0 ? "No programme produced a positive credit." :
            "Programmes with a positive statutory credit, largest lifetime credit first."));
        if (hits.Count != 0)
        {
            blocks.Add(Table(["Programme", "Jurisdiction", "Qualifying jobs", "Annual credit", "Lifetime credit"],
                hits.Select(hit => new[] { T(hit!["credit_name"]), T(hit["jurisdiction"]), F(hit["qualifying_jobs"], "headcount"),
                    F(hit["annual_credit_usd"], "money"), F(hit["lifetime_credit_usd"], "money") })));
        }
        return new CapabilityResult("client_discovery", facts) { Blocks = blocks };
    }

    private static CapabilityResult History(CapabilityRead read)
    {
        var facts = read.Facts;
        var current = facts["current"]!;
        return new CapabilityResult("claim_cell_history", facts)
        {
            Blocks =
            [
                Block("heading", $"{T(current["program_code"])} · TY{F(current["tax_year"], "year")}"),
                Table(["From", "Status", "Identified", "Claimed", "Decided by"], A(facts["history"]).Select(entry => new[]
                {
                    F(entry!["effective_from"], "date"), T(entry["status"]), F(entry["identified_usd"], "money"),
                    F(entry["claimed_usd"], "money"), T(entry["decided_by"]),
                })),
            ],
            Warnings = B(current["provenance_verified"]) ? [] : ["The claimed figure is an unverified assertion, not a filing."],
        };
    }
}
