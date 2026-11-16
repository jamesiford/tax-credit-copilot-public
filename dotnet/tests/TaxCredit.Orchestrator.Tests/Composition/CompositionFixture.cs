using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Tests.Composition;

internal static class CompositionFixture
{
    internal static CompositionRun Credit(string label = "credit_min_max", string method = "min_max") =>
        new("client_eligibility", new JsonObject { ["tax_year"] = 2023, ["method"] = method, ["client_id"] = 2001 },
            new CapabilityResult("client_eligibility", JsonNode.Parse("""
                {"credit":{"annual_credit_usd":"3640.50","average_headcount":"14.73","qualifying_jobs":null},
                 "population":{"min_max_eligible":51,"ratio":"0.125"},
                 "snapshot":{"tax_year":2023,"begin":"2023-07-28"},"citation":"Code 48-7-40.26"}
                """)!.AsObject())
            {
                Blocks =
                [
                    CapabilityResult.Block("heading", "Georgia Jobs Tax Credit"),
                    CapabilityResult.Block("table", rows:
                    [
                        ["Measure", "Value"], ["Annual credit", "$3,640.50"],
                        ["Average headcount", "14.73"], ["Eligible employees", "51"],
                    ]),
                    CapabilityResult.Block("paragraph", "Citation: Code 48-7-40.26"),
                ],
                Provenance = CapabilityResult.Evidence("synthetic-run-42", "rules/example/2023.json",
                    trailSha256: "abcdef0123456789abcdef0123456789"),
            }, label);

    internal static CompositionRun Employee() =>
        new("data_query", new JsonObject { ["client_id"] = 2001 },
            new CapabilityResult("data_query", JsonNode.Parse("""
                {"row_count":2,"columns":["record_token","total_wages","method"],
                 "rows":[{"record_token":"synthetic-record-990001","total_wages":"613.47","method":"private-method"},
                         {"record_token":"synthetic-record-990002","total_wages":"727.93","method":"private-method"}]}
                """)!.AsObject())
            {
                UserOnlyFacts = ["rows"],
                Warnings = ["Private row synthetic-record-990001 has wage 613.47."],
                Blocks =
                [
                    CapabilityResult.Block("heading", "Query result"),
                    CapabilityResult.Block("table", rows:
                    [
                        ["Record", "Wages", "Method"], ["synthetic-record-990001", "613.47", "private-method"],
                        ["synthetic-record-990002", "727.93", "private-method"],
                    ], audience: "user"),
                ],
            }, "data_query");

    internal static string Placeholder(string path, string? format = null) =>
        FactPlaceholders.PlaceholderFor("credit_min_max." + path, format);
}
