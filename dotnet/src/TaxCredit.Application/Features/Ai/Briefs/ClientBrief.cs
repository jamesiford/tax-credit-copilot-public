using System.Globalization;
using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Briefs.BriefValues;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>Finished qualification and open-year pace remain different claims.</summary>
public static class ClientBrief
{
    /// <summary>Shapes stored unit-year readings and the page's already-summed totals.</summary>
    public static PageBrief Build(JsonObject payload, string clientName, IReadOnlyList<int>? placeholderYears = null)
    {
        ArgumentNullException.ThrowIfNull(payload);
        var items = Rows(payload["items"]).ToArray();
        if (items.Length == 0) { return NotCalculated("client", clientName, payload); }
        var locations = new List<JsonObject>();
        int? openYear = null;
        foreach (var group in items.GroupBy(r => Text(r["worksite_id"])).OrderBy(g => g.Key, StringComparer.Ordinal))
        {
            var rows = group.OrderBy(r => Integer(r["tax_year"])).ToArray();
            var closed = rows.Where(r => Text(r["status"]) != "in_progress").ToArray();
            var opened = rows.FirstOrDefault(r => Text(r["status"]) == "in_progress");
            var last = closed.LastOrDefault();
            var baseline = rows.FirstOrDefault(r => True(r["is_base_year"]));
            var entry = new JsonObject
            {
                ["location"] = group.Key,
                ["base_year"] = baseline?["tax_year"]?.DeepClone(),
                ["designation"] = last?["designation"]?.DeepClone()
            };
            if (last is not null)
            {
                entry["latest_finished_year"] = Integer(last["tax_year"]);
                entry["latest_reading"] = Text(last["status"]).Replace('_', ' ');
                entry["latest_net_new_jobs"] = One(last["net_new_vs_base"]);
            }
            if (opened is not null)
            {
                openYear = Integer(opened["tax_year"]);
                entry["open_year_reading"] = True(opened["qualified"]) ? "on track" : "behind pace";
                entry["open_year_net_new_jobs"] = One(opened["net_new_vs_base"]);
                entry["open_year_closed_months"] = opened["months_reachable"]?.DeepClone();
            }
            var declines = closed.Where(r => Text(r["status"]) == "below_minimum").Select(r => Integer(r["tax_year"])).ToArray();
            if (declines.Length > 0) { entry["years_below_minimum"] = new JsonArray(declines.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray()); }
            locations.Add(entry);
        }
        var totals = Rows(payload["unit_totals"]).ToArray();
        var claimable = PyTotal(totals, "total_annual_credit_usd");
        var lifetime = PyTotal(totals, "total_tranche_lifetime_usd");
        var finished = items.Where(r => Text(r["status"]) != "in_progress").Select(r => Integer(r["tax_year"])).Distinct().Order().ToArray();
        var facts = Facts(locations, finished, openYear, claimable, lifetime);
        var caveats = new List<string> { "Base years are inferred from payroll and designations are prototype data." };
        if (openYear is { } year)
        {
            caveats.Add(string.Create(CultureInfo.InvariantCulture, $"TY{year} is open: read on its closed months, never priced; 'on track' is a forecast, not a qualification."));
            if (placeholderYears?.Contains(year) == true)
            {
                caveats.Add(string.Create(CultureInfo.InvariantCulture, $"TY{year}'s wage floor is a placeholder carried forward from TY{year - 1} until Georgia publishes it."));
            }
        }
        return new("client", clientName, facts[0], facts, caveats, new JsonObject
        {
            ["locations"] = new JsonArray(locations.Select(v => (JsonNode?)v).ToArray()),
            ["claimable_usd"] = Math.Round(claimable, MidpointRounding.ToEven),
            ["if_maintained_usd"] = Math.Round(lifetime, MidpointRounding.ToEven),
            ["finished_years"] = new JsonArray(finished.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray()),
            ["open_year"] = openYear
        });
    }

    private static double PyTotal(JsonObject[] totals, string column) =>
        TaxCredit.Domain.Numerics.PySum.Sum(totals.Select(t => Number(t[column]) ?? 0).ToArray());

    private static List<string> Facts(List<JsonObject> locations, int[] finished, int? openYear, double claimable, double lifetime)
    {
        var qualifying = locations.Count(l => Text(l["latest_reading"]) == "above minimum");
        var below = locations.Where(l => Text(l["latest_reading"]) == "below minimum").ToArray();
        var facts = new List<string>
        {
            string.Create(CultureInfo.InvariantCulture, $"{Plural(locations.Count, "location")}; in its latest finished year, {qualifying} qualify and {below.Length} are below the minimum.")
        };
        if (claimable != 0 && finished.Length > 0)
        {
            var span = finished.Length > 1
                ? string.Create(CultureInfo.InvariantCulture, $"TY{finished[0]}\u2013TY{finished[^1]}")
                : string.Create(CultureInfo.InvariantCulture, $"TY{finished[0]}");
            facts.Add($"{Usd(JsonValue.Create(claimable))} claimable across {span}; {Usd(JsonValue.Create(lifetime))} if maintained.");
        }
        facts.AddRange(below.Select(l => $"{l["location"]} was below the minimum in TY{l["latest_finished_year"]} ({l["latest_net_new_jobs"]} net-new jobs against its TY{l["base_year"]} base)."));
        if (openYear is not null)
        {
            var onTrack = locations.Count(l => Text(l["open_year_reading"]) == "on track");
            var behind = locations.Where(l => Text(l["open_year_reading"]) == "behind pace").ToArray();
            facts.Add(string.Create(CultureInfo.InvariantCulture, $"TY{openYear} is still open: {onTrack} of {onTrack + behind.Length} locations on track so far."));
            facts.AddRange(behind.Select(l => $" {l["location"]} is behind pace in TY{openYear} ({l["open_year_net_new_jobs"]} net-new jobs so far).".TrimStart()));
        }
        return facts;
    }
}
