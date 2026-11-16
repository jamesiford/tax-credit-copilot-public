using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static partial class CapabilityRender
{
    private static readonly Dictionary<string, string> BandNames = new(StringComparer.Ordinal)
    {
        ["exposed"] = "Exposed",
        ["on_the_line"] = "On the line",
        ["declining"] = "Declining",
        ["unclaimed_at_scale"] = "Identified",
        ["not_assessed"] = "Not assessed",
        ["settled"] = "Nothing found",
        ["unavailable"] = "Unavailable",
    };

    internal static CapabilityResult Render(string tool, CapabilityRead read)
    {
        var result = tool switch
        {
            "book_rank" => Book(read),
            "client_situation" => Situation(read),
            "client_eligibility" => Eligibility(read),
            "client_trend" => Trend(read),
            "client_at_risk" => Risk(read),
            "client_discovery" => Discovery(read),
            "claim_cell_history" => History(read),
            "simulate" => Simulate(read),
            "calc_walkthrough" => Walkthrough(read),
            "employee_drill" => Employee(read),
            "findings_list" => Findings(read),
            "program_catalog" => Programs(read),
            "run_batch_list" or "run_batch_status" => Runs(tool, read),
            "claim_package_link" => Package(read),
            "claim_package_redeem" => new CapabilityResult(tool, read.Facts),
            _ => throw new CapabilityException(501, "not_implemented", $"No renderer is built for {tool}."),
        };
        return result with
        {
            Provenance = read.Provenance ?? result.Provenance,
            Blocks = read.Blocks ?? result.Blocks,
            Warnings = result.Warnings.Concat(read.Warnings ?? []).Distinct(StringComparer.Ordinal).ToArray(),
            UserOnlyFacts = result.UserOnlyFacts.Concat(read.UserOnlyFacts ?? []).Distinct(StringComparer.Ordinal).ToArray(),
        };
    }

    private static string F(JsonNode? value, string kind = "number") => CapabilityFormat.Render(value, kind);
    private static string T(JsonNode? value) => value?.GetValue<string>() ?? "—";
    private static bool B(JsonNode? value) => value?.GetValue<bool>() == true;
    private static JsonArray A(JsonNode? value) => value as JsonArray ?? [];
    private static JsonObject Table(IEnumerable<string> header, IEnumerable<IEnumerable<string>> rows, string audience = "both") =>
        Block("table", rows: new[] { header }.Concat(rows), audience: audience);

    private static CapabilityResult Book(CapabilityRead read)
    {
        var page = read.Facts;
        var items = A(page["items"]);
        var unavailable = items.Where(row => B(row!["data_unavailable"]))
            .Select(row => T(row!["client_name"] ?? JsonValue.Create($"Account {row["client_id"]}"))).ToArray();
        var ranked = items.Where(row => !B(row!["data_unavailable"])).ToArray();
        if (ranked.Length == 0)
        {
            var message = unavailable.Length != 0
                ? "Claim figures are unavailable right now, so the clients cannot be ranked. That does not mean any client was assessed with no result, and it does not mean none was assessed."
                : "No client has been assessed yet. There is nothing to rank — that is not the same as nobody being worth calling.";
            var facts = new JsonObject { ["calculated"] = false, ["message"] = message };
            if (unavailable.Length != 0)
            {
                facts["unavailable"] = true;
                facts["unavailable_clients"] = Strings(unavailable);
                facts["degraded"] = page["degraded"]?.DeepClone() ?? new JsonArray();
            }
            return new CapabilityResult("book_rank", facts)
            {
                Blocks = [Block("paragraph", message)],
                Provenance = Evidence(source: "recorded claims; no run"),
            };
        }
        return RankedBook(page, ranked, unavailable);
    }

    private static CapabilityResult RankedBook(JsonObject page, JsonNode?[] ranked, string[] unavailable)
    {
        var clients = new JsonArray(ranked.Select((row, index) => (JsonNode)new JsonObject
        {
            ["position"] = index + 1,
            ["client_name"] = row!["client_name"]?.DeepClone() ?? JsonValue.Create($"Account {row["client_id"]}"),
            ["reason"] = BandNames.GetValueOrDefault(T(row["priority_band"]), T(row["priority_band"])),
            ["program_code"] = row["program_code"]?.DeepClone(),
            ["tax_year"] = row["tax_year"]?.DeepClone(),
            ["identified_usd"] = row["identified_usd"]?.DeepClone(),
            ["jobs_margin"] = row["jobs_margin"]?.DeepClone(),
            ["credit_earned_on_trend_usd"] = T(row["priority_band"]) == "declining" ? row["trend"]?["credit_earned_usd"]?.DeepClone() : null,
            ["provenance_verified"] = row["provenance_verified"]?.DeepClone(),
        }).ToArray());
        var unverified = clients.Any(row => row!["provenance_verified"] is { } verified && !B(verified));
        var facts = new JsonObject
        {
            ["calculated"] = true,
            ["total_clients"] = page["total_clients"]?.DeepClone(),
            ["assessed_clients"] = page["assessed_clients"]?.DeepClone(),
            ["clients"] = clients,
            ["ranking_note"] = "Ordered by what inaction costs, not by size, and in the same order as the page. 'On the line' outranks 'Identified' because a threshold missed at year end is gone, while an unclaimed credit is recoverable retroactively. 'Declining' is a forecast about a year nobody has filed, not a finding against a filed return.",
            ["claimed_is_unverified"] = unverified,
        };
        var blocks = new JsonArray();
        if (unavailable.Length != 0)
        {
            facts["unavailable_clients"] = Strings(unavailable);
            facts["degraded"] = page["degraded"]?.DeepClone() ?? new JsonArray();
            blocks.Add(Block("paragraph", $"{unavailable.Length} client(s) are unavailable (their claim figures cannot be read) and are not ranked: {string.Join(", ", unavailable)}. Unavailable is not the same as not assessed."));
        }
        var coverage = page["assessed_clients"] is null ? "How many clients have been assessed is unavailable right now. " :
            $"{F(page["assessed_clients"], "count")} of {F(page["total_clients"], "count")} clients have been assessed. ";
        blocks.Add(Block("paragraph", coverage + "Ranked by what inaction costs, in the order the page shows."));
        blocks.Add(Table(["#", "Client", "Reason", "Programme", "Tax year", "Identified", "Jobs margin"],
            clients.Select(row => new[] { F(row!["position"], "count"), T(row["client_name"]), T(row["reason"]),
                T(row["program_code"]), F(row["tax_year"], "year"), F(row["identified_usd"], "money"), F(row["jobs_margin"]) })));
        return new CapabilityResult("book_rank", facts)
        {
            Blocks = blocks,
            Provenance = Evidence(source: "recorded claims; no run"),
            Warnings = unverified ? ["Some rows rest on a claimed figure that is an unverified assertion, not a filing. The ranking uses the identified figure, which is computed."] : [],
        };
    }
}
