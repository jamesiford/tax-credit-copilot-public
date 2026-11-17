using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static partial class CapabilityRender
{
    private const string VerificationNote = "Not verified. A rule pack that validates is well-formed, not legally correct: a person must verify each value against the primary source.";

    private static CapabilityResult Programs(CapabilityRead read)
    {
        var facts = read.Facts;
        JsonArray blocks;
        if (facts["programs"] is JsonArray programs)
        {
            blocks =
            [
                Block("heading", "Programs the platform knows"),
                Block("paragraph", $"{F(facts["total"], "count")} programs are registered; {F(facts["calculable"], "count")} can be calculated for their authored years."),
                Table(["Program", "State", "Lifecycle", "Authored years", "Calculable", "Clients"],
                    programs.Select(program => new[]
                    {
                        $"{T(program!["name"])} ({T(program["code"])})", T(program["state"] ?? program["jurisdiction"]?["level"]),
                        T(program["lifecycle"]), Years(program["authored_years"]),
                        B(program["calculable"]) ? "Yes" : $"No: {T(program["not_calculable_reason"])}",
                        program["engagement"] is { } engagement ? $"{F(engagement["clients"], "count")} ({F(engagement["in_scope"], "count")} in scope)" : "—",
                    })),
                Block("callout", VerificationNote),
            ];
        }
        else
        {
            blocks =
            [
                Block("heading", $"{T(facts["name"])} ({T(facts["code"])})"),
                Block("paragraph", $"Lifecycle: {T(facts["lifecycle"])}. Authored years: {Years(facts["authored_years"])}. Pack file {T(facts["pack"]!["file"])}."),
            ];
            if (A(facts["blockers"]).Count != 0)
            {
                blocks.Add(Block("bullets", rows: A(facts["blockers"]).Select(value => new[] { T(value) })));
            }
            if (A(facts["years"]).Count != 0)
            {
                blocks.Add(Table(["Tax year", "Still flagged unverified", "Source"], A(facts["years"]).Select(year => new[]
                {
                    F(year!["tax_year"], "year"), B(year["unverified"]) ? "Yes" : "No", T(year["source"]),
                })));
            }
            blocks.Add(Block("callout", VerificationNote));
        }
        return new CapabilityResult("program_catalog", facts)
        {
            Blocks = blocks,
            Provenance = Evidence(source: "program registry and rule packs"),
            Warnings = facts["programs"] is not null && !B(facts["engagement_available"]) ?
                ["Engagement counts are unavailable right now; they are not zero."] : [],
        };
    }

    private static string Years(JsonNode? years) => A(years).Count == 0 ? "none authored" :
        string.Join(", ", A(years).Select(year => F(year, "year")));
}
