using System.Text.Json;
using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static partial class CapabilityRender
{
    private static readonly string[] RunOutcomes = ["queued", "running", "succeeded", "skipped", "failed", "cancelled"];
    private static CapabilityResult Simulate(CapabilityRead read)
    {
        var facts = read.Facts;
        var fields = new (string Label, string Key, string Format)[]
        {
            ("Average headcount", "average_headcount", "headcount"), ("Net new vs base", "net_new_vs_base", "headcount"),
            ("Annual credit", "annual_credit_usd", "money"), ("Credit over the series", "series_credit_usd", "money"),
        };
        var blocks = new JsonArray(
            Block("heading", $"{T(facts["scope"]!["worksite_id"])} · TY{F(facts["scope"]!["tax_year"], "year")}"),
            Block("paragraph", T(facts["detail"])),
            Table(["Measure", "Baseline", "Projected", "Change"], fields.Select(field => new[]
            {
                field.Label, F(facts["baseline"]![field.Key], field.Format), F(facts["projected"]![field.Key], field.Format),
                F(facts["delta"]![field.Key], field.Format),
            })));
        if (facts["run_rate"] is JsonObject runRate)
        {
            blocks.Add(Block("callout", T(runRate["note"])));
        }
        return new CapabilityResult("simulate", facts) { Blocks = blocks };
    }

    private static CapabilityResult Walkthrough(CapabilityRead read)
    {
        var facts = read.Facts;
        var blocks = new JsonArray(Block("heading", facts["title"] is null ? "Calculation" : T(facts["title"])));
        if (facts["citation"] is not null)
        {
            blocks.Add(Block("paragraph", $"Citation: {T(facts["citation"])}"));
        }
        if (A(facts["steps"]).Count != 0)
        {
            blocks.Add(Table(["Step", "Inputs", "Formula", "Output", "Citation"], A(facts["steps"]).Select(step => new[]
            {
                T(step!["step"]), Inline(step["inputs"]!.AsObject()), T(step["formula"]),
                Inline(step["output"]!.AsObject()), T(step["citation"]),
            })));
        }
        if (facts["evidence_hash"] is not null)
        {
            blocks.Add(Block("paragraph", $"Evidence hash: {T(facts["evidence_hash"])}"));
        }
        return new CapabilityResult("calc_walkthrough", facts) { Blocks = blocks };
    }

    private static string Inline(JsonObject fields) => string.Join(", ", fields.OrderBy(entry => entry.Key, StringComparer.Ordinal)
        .Select(entry => $"{entry.Key}={InlineValue(entry.Value)}"));

    private static string InlineValue(JsonNode? value) => value switch
    {
        null => "—",
        JsonValue when value.GetValueKind() == JsonValueKind.Number => F(value),
        JsonValue when value.GetValueKind() == JsonValueKind.String => T(value),
        _ => value.ToJsonString(),
    };

    private static CapabilityResult Employee(CapabilityRead read) => new("employee_drill", read.Facts)
    {
        Blocks =
        [
            Block("heading", $"Employee derivation · TY{F(read.Facts["context"]?["tax_year"] ?? read.Facts["tax_year"], "year")}"),
            Block("paragraph", "This employee is identified by an opaque record token. The derivation below is read from the run that decided eligibility; it is not recomputed."),
        ],
        Warnings = ["Sensitive: this result describes an individual employee."],
        UserOnlyFacts = read.Facts.Select(entry => entry.Key).Except(["run", "not_available", "context"], StringComparer.Ordinal).ToArray(),
    };

    private static CapabilityResult Findings(CapabilityRead read)
    {
        var facts = read.Facts;
        var summary = facts["summary"]!;
        var blocks = B(summary["none_found"])
            ? new JsonArray(Block("paragraph", "No findings were raised for this client-year."))
            : new JsonArray(
                Block("paragraph", $"{F(summary["requires_decision"], "count")} of {F(summary["total"], "count")} decisions are open, covering {F(summary["instances"], "count")} underlying records."),
                Table(["Finding", "Grain", "Records", "Status"], A(facts["findings"]).Select(finding => new[]
                {
                    T(finding!["title"]), T(finding["grain"]) == "policy" ? "Policy" : "Instance",
                    F(finding["population"]?["instances"], "count"), B(finding["requires_decision"]) ? "Open" : "Decided",
                })));
        return new CapabilityResult("findings_list", facts)
        {
            Blocks = blocks,
            Warnings = ["Sensitive: instance findings identify individual employees."],
            UserOnlyFacts = facts.ContainsKey("findings") ? ["findings"] : [],
        };
    }

    private static CapabilityResult Package(CapabilityRead read) => new("claim_package_link", read.Facts)
    {
        Blocks =
        [
            Block("heading", "Claim package download"),
            Table(["File", "SHA-256"], [new[] { T(read.Facts["file_name"]), T(read.Facts["sha256"]) }]),
            Block("callout", $"The link works once, for you only, for {F(read.Facts["ticket_minutes"], "count")} minutes."),
        ],
    };

    private static CapabilityResult Runs(string tool, CapabilityRead read)
    {
        var facts = read.Facts;
        if (tool == "run_batch_list")
        {
            return new CapabilityResult(tool, facts)
            {
                Blocks = [Block("heading", "Recent run batches"),
                    Table(["Batch", "Kind", "Status", "Done", "Started by"], A(facts["items"]).Select(batch => new[]
                    {
                        T(batch!["batch_id"])[..Math.Min(8, T(batch["batch_id"]).Length)], T(batch["kind"]).Replace('_', ' '),
                        T(batch["status"]), $"{F(batch["progress"]!["done"], "count")} of {F(batch["progress"]!["total"], "count")}",
                        T(batch["requested_by"]),
                    }))],
            };
        }
        var blocks = new JsonArray(Block("heading", $"Run batch: {T(facts["status"])}"),
            Block("paragraph", $"{F(facts["progress"]!["done"], "count")} of {F(facts["progress"]!["total"], "count")} runs finished. Started by {T(facts["requested_by"])}; kind {T(facts["kind"]).Replace('_', ' ')}."),
            Table(["Outcome", "Items"], RunOutcomes
                .Select(status => new[] { char.ToUpperInvariant(status[0]) + status[1..], F(facts["counts"]![status], "count") })));
        foreach (var failure in A(facts["failures"]))
        {
            blocks.Add(Block("paragraph", $"{F(failure!["count"], "count")} failed with {T(failure["dependency"])}: {T(failure["message"])}"));
        }
        return new CapabilityResult(tool, facts) { Blocks = blocks };
    }
}
