using System.Globalization;
using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Briefs.BriefValues;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>The portfolio owner decides rank; narration cannot reorder or score it.</summary>
public static class PortfolioBrief
{
    /// <summary>Shapes the same unfiltered page payload the book displays.</summary>
    public static PageBrief Build(JsonObject book)
    {
        ArgumentNullException.ThrowIfNull(book);
        var items = Rows(book["items"]).ToArray();
        var total = Integer(book["total_clients"], items.Length);
        int? assessed = book["assessed_clients"] is null ? null : Integer(book["assessed_clients"]);
        var unavailable = items.Where(r => True(r["data_unavailable"])).ToArray();
        var ranked = items.Where(r => !True(r["data_unavailable"])).ToArray();
        var clients = new JsonArray();
        var facts = new List<string>
        {
            assessed is null
                ? $"{Plural(total, "client")} in the book; how many are assessed is unavailable right now."
                : string.Create(CultureInfo.InvariantCulture, $"{Plural(total, "client")} in the book, {assessed} assessed.")
        };
        for (var index = 0; index < ranked.Length; index++)
        {
            var row = ranked[index];
            var fact = ClientFact(index + 1, row);
            facts.Add(fact);
            clients.Add(new JsonObject
            {
                ["position"] = index + 1,
                ["client"] = Name(row),
                ["industry"] = row["industry"]?.DeepClone(),
                ["reason"] = Label(row),
                ["fact"] = fact
            });
        }
        var caveats = new List<string>
        {
            "The ranking is by reason to act, not by dollar value: 'On the line' outranks 'Identified' because a threshold missed at year end is gone, while an unclaimed credit is recoverable retroactively.",
            "'Declining' is a forecast about a year nobody has filed, not a finding."
        };
        AddCoverage(total, assessed, unavailable, facts, caveats);
        return new("portfolio", "the whole book of clients", facts[0], facts, caveats,
            new JsonObject { ["total_clients"] = total, ["assessed_clients"] = assessed, ["clients"] = clients });
    }

    private static void AddCoverage(int total, int? assessed, JsonObject[] unavailable, List<string> facts, List<string> caveats)
    {
        if (assessed is { } count && total > count + unavailable.Length)
        {
            caveats.Add(string.Create(CultureInfo.InvariantCulture, $"{total - count - unavailable.Length} client(s) have not been assessed: that is not a zero."));
        }
        if (unavailable.Length == 0) { return; }
        facts.Add($"Claim figures are unavailable for {Plural(unavailable.Length, "client")} ({string.Join(", ", unavailable.Select(Name))}); they are not ranked.");
        caveats.Add("Unavailable is not the same as not assessed and not a zero: the claim figures are unavailable, so nothing is known about those clients' assessment.");
    }

    private static string Name(JsonObject row) => Text(row["client_name"], "Account " + Text(row["client_id"]));
    private static string Label(JsonObject row) => BandLabels.GetValueOrDefault(Text(row["priority_band"]), Text(row["priority_band"], "unranked"));

    private static string ClientFact(int position, JsonObject row)
    {
        var fact = string.Create(CultureInfo.InvariantCulture, $"{position}. {Name(row)}: {Label(row)}");
        if (row["program_code"] is not null && row["tax_year"] is not null)
        {
            fact += $" ({row["program_code"]} TY{row["tax_year"]})";
        }
        if (Text(row["priority_band"]) == "on_the_line" && Number(row["jobs_margin"]) is { } margin)
        {
            fact += $", {Fixed(Math.Abs(margin), 2)} jobs {(margin < 0 ? "short of" : "over")} the minimum";
        }
        else if (Text(row["priority_band"]) == "declining" && row["trend"] is JsonObject trend)
        {
            if (Number(trend["fallen_by"]) is { } fallen) { fact += $", down {Fixed(fallen, 1)} jobs since TY{trend["peak_tax_year"]}"; }
            if (True(trend["below_base"])) { fact += ", now below its base year"; }
            if (trend["credit_earned_usd"] is not null) { fact += $", {Usd(trend["credit_earned_usd"])} already earned"; }
        }
        else if (Number(row["identified_usd"]) is { } money && money != 0)
        {
            fact += $", {Usd(row["identified_usd"])} identified";
        }
        return fact;
    }
}
