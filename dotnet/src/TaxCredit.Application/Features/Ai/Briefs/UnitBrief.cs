using System.Globalization;
using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Briefs.BriefValues;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>A unit summary describes counted and near-miss cohorts separately.</summary>
public static class UnitBrief
{
    private static readonly string[] Months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

    /// <summary>Person-level details stay in the local brief; the narrator receives a redacted projection.</summary>
    public static PageBrief Build(JsonObject payload, string clientName, int? month = null, bool placeholder = false)
    {
        ArgumentNullException.ThrowIfNull(payload);
        if (payload["unit"] is not JsonObject unit) { return NotCalculated("unit", clientName, payload); }
        if (month is < 1 or > 12) { throw new ArgumentOutOfRangeException(nameof(month)); }
        var year = Integer(payload["year"], Integer(unit["tax_year"]));
        var site = Text(unit["worksite_id"], Text(payload["unit_id"]));
        var floor = Number(Object(payload["thresholds"])["min_weekly_hours"]);
        var counted = Integer(payload["total_unfiltered"], Rows(payload["employees"]).Count());
        var near = Rows(payload["near_threshold"]).ToArray();
        var within = near.Where(r => floor is { } min && Number(r["avg_weekly_hours"]) is { } hours && hours >= min - 5).ToArray();
        var inProgress = Text(unit["status"]) == "in_progress";
        var reading = inProgress ? True(unit["qualified"]) ? "on track" : "behind pace" : Text(unit["status"]).Replace('_', ' ');
        var when = month is { } index
            ? string.Create(CultureInfo.InvariantCulture, $"in {Months[index - 1]} TY{year}")
            : string.Create(CultureInfo.InvariantCulture, $"in TY{year}");
        var facts = new List<string>
        {
            string.Create(CultureInfo.InvariantCulture, $"{site}: {counted} employees counted {when}."),
            $"Average headcount {One(unit["average_headcount"])} against a base of {Text(unit["base_average_headcount"], "None")}; reading: {reading}"
                + (inProgress ? $" over {unit["months_reachable"]} closed months." : ".")
        };
        if (unit["designation"] is not null) { facts.Add(string.Create(CultureInfo.InvariantCulture, $"Designation {unit["designation"]} in TY{year} (prototype data, shown not applied).")); }
        if (unit["net_new_vs_base"] is not null && !True(unit["is_base_year"]))
        {
            facts.Add($"{One(unit["net_new_vs_base"])} net-new jobs against a minimum of {One(unit["threshold"])}.");
        }
        if (floor is { } hoursFloor)
        {
            facts.Add(string.Create(CultureInfo.InvariantCulture, $"{within.Length} more employees are within 5 hrs/week of the {General(hoursFloor)}-hour floor; {near.Length} are ineligible in all."));
            foreach (var row in within.OrderByDescending(r => Number(r["avg_weekly_hours"]) ?? 0).Take(3))
            {
                var extra = Number(row["additional_weekly_hours"]);
                facts.Add($"Employee {row["employee_id"]} averages {Fixed(Number(row["avg_weekly_hours"])!.Value, 2)} hrs/week"
                    + (extra is not null and not 0 ? $" and needs {Fixed(extra.Value, 2)} more to qualify." : "."));
            }
        }
        var caveats = new List<string>();
        if (inProgress) { caveats.Add(string.Create(CultureInfo.InvariantCulture, $"TY{year} is open: read on its closed months; nothing is priced yet.")); }
        if (placeholder) { caveats.Add(string.Create(CultureInfo.InvariantCulture, $"TY{year}'s wage floor is a placeholder carried forward from TY{year - 1}.")); }
        return new("unit", $"{clientName} \u00b7 {site}", facts[0], facts, caveats, new JsonObject
        {
            ["location"] = site,
            ["tax_year"] = year,
            ["month"] = month,
            ["counted"] = counted,
            ["reading"] = reading,
            ["within_band"] = within.Length,
            ["ineligible"] = near.Length
        });
    }
}
