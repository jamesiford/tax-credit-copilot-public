using System.Globalization;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;

namespace TaxCredit.Orchestrator.Tests.Support;

internal static class FakeEnvelopes
{
    internal static CapabilityResult Read(string tool, JsonObject args) => tool switch
    {
        "book_rank" => Book(),
        "client_eligibility" => Eligibility(args),
        "client_trend" => Trend(),
        _ => Simple(tool, args),
    };

    private static CapabilityResult Simple(string tool, JsonObject args) => new(tool, new JsonObject
    {
        ["items"] = new JsonObject { ["total"] = 3, ["annual_value_usd"] = "31500.00" },
        ["tax_year"] = args["tax_year"]?.DeepClone(),
    })
    {
        Blocks = new JsonArray(CapabilityResult.Block("heading", CultureInfo.InvariantCulture.TextInfo.ToTitleCase(tool.Replace('_', ' '))),
            CapabilityResult.Block("table", rows: [new[] { "Measure", "Value" }, new[] { "Items", "3" }, new[] { "Annual value", "$31,500" }])),
        Provenance = CapabilityResult.Evidence(source: "recorded claims; no run"),
    };

    private static CapabilityResult Book()
    {
        string[] values = ["140000", "40495", "9900"];
        var rows = FakeGateway.Book.Select((row, index) => new JsonObject
        {
            ["name"] = row.Name,
            ["band"] = "Identified",
            ["identified_usd"] = values[index],
        }).ToArray();
        return new CapabilityResult("book_rank", new JsonObject { ["rows"] = new JsonArray(rows.Cast<JsonNode>().ToArray()) })
        {
            Blocks = new JsonArray(CapabilityResult.Block("heading", "Who to call"),
                CapabilityResult.Block("table", rows: new[] { new[] { "Client", "Band", "Identified" } }.Concat(rows.Select(row =>
                    new[] { row["name"]!.ToString(), "Identified", CapabilityFormat.Render(row["identified_usd"], "money") })))),
            Provenance = CapabilityResult.Evidence(source: "recorded claims; no run"),
        };
    }

    private static CapabilityResult Eligibility(JsonObject args)
    {
        var pay = args["method"]?.ToString() == "pay_period";
        var credit = new JsonObject
        {
            ["credit_name"] = "Georgia Jobs Tax Credit",
            ["average_headcount"] = pay ? "494.25" : "375.53",
            ["prior_period_average_headcount"] = "310.50",
            ["qualifying_jobs"] = pay ? "183.75" : "65.03",
            ["annual_credit_usd"] = pay ? "643125.00" : "227605.00",
            ["lifetime_credit_usd"] = pay ? "3215625.00" : "1138025.00",
            ["benefit_period_years"] = 5,
            ["citation"] = "O.C.G.A. 48-7-40.1",
        };
        return new CapabilityResult("client_eligibility", new JsonObject
        {
            ["snapshot"] = new JsonObject
            {
                ["selected_client_id"] = args["client_id"]!.DeepClone(),
                ["selected_tax_year"] = args["tax_year"]!.DeepClone(),
                ["calculated"] = true,
            },
            ["credit"] = credit,
        })
        {
            Blocks = new JsonArray(CapabilityResult.Block("heading", $"Georgia Jobs Tax Credit · TY{args["tax_year"]}"),
                CapabilityResult.Block("table", rows:
                [
                    new[] { "Measure", "Value" },
                    new[] { "Average headcount", CapabilityFormat.Render(credit["average_headcount"], "headcount") },
                    new[] { "Qualifying jobs", CapabilityFormat.Render(credit["qualifying_jobs"], "headcount") },
                    new[] { "Annual credit", CapabilityFormat.Render(credit["annual_credit_usd"], "money") },
                    new[] { "Lifetime credit", CapabilityFormat.Render(credit["lifetime_credit_usd"], "money") },
                ])),
            Provenance = CapabilityResult.Evidence(runId: "run-0001", rulePackVersion: "rules/ga_jtc/2023.json",
                trailSha256: string.Concat(Enumerable.Repeat("ab", 32)), source: "tcc_gold"),
        };
    }

    private static CapabilityResult Trend() => new("client_trend", new JsonObject
    {
        ["years"] = new JsonArray(new JsonObject { ["tax_year"] = 2022, ["annual_average"] = "410.13" },
            new JsonObject { ["tax_year"] = 2023, ["annual_average"] = "494.25" }),
        ["eligible_every_year_since_base"] = null,
    })
    {
        Blocks = new JsonArray(CapabilityResult.Block("heading", "Trend"), CapabilityResult.Block("table", rows:
            [new[] { "Tax year", "Annual average" }, new[] { "2022", "410.13" }, new[] { "2023", "494.25" }])),
        Provenance = CapabilityResult.Evidence(runId: "run-0001", trailSha256: string.Concat(Enumerable.Repeat("cd", 32))),
    };
}
